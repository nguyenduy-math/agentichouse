"""PageIndexService — manages PageIndex tree indices for one policy domain.

PageIndex (VectifyAI) converts PDFs/Markdown into hierarchical tree structures
(like a table of contents optimized for LLMs) and navigates them via reasoning
instead of vector similarity. This service wraps that workflow:

  1. index_document() — runs PageIndex CLI (via subprocess) to produce a JSON tree
  2. query()          — loads JSON trees + uses Gemini to navigate and answer

Context-engineering notes (audit refs):
  * Prompts come from app.prompts and respect settings.response_language (A2, A3).
  * The agent's own persona threads into the answer prompt (D3) and conversation
    history threads into navigation + answering (D1).
  * Citations are taken from the structured answer (GroundedAnswer) so they reflect
    the text the model actually used, not the navigation step's guesses (B4).
  * Truncation is token-aware via app.context_budget; depth / section caps come from
    settings instead of inline magic numbers (C1, C3, C4).

PageIndex is sync-heavy (LLM calls during indexing) so we wrap with
asyncio.to_thread() to avoid blocking the FastAPI event loop.

Installation:
    pip install git+https://github.com/VectifyAI/PageIndex.git
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from google import genai
from google.genai import types

from app import prompts
from app.config import settings
from app.context_budget import fit_sections, log_prompt_size, truncate_to_tokens
from app.schemas import GroundedAnswer, TreeNavigation

logger = logging.getLogger(__name__)

_REGISTRY_FILE = "registry.json"

_NAV_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=TreeNavigation,
    temperature=0.0,
)
_ANSWER_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=GroundedAnswer,
    temperature=0.2,
)


class PageIndexResult:
    def __init__(self, answer: str, citations: list[dict]) -> None:
        self.answer = answer
        self.citations = citations  # list of {document, page, section, domain}


class PageIndexService:
    def __init__(self, index_dir: Path, domain: str) -> None:
        self._index_dir = index_dir
        self._domain = domain
        self._registry: dict[str, str] = {}
        self._client: genai.Client | None = None
        index_dir.mkdir(parents=True, exist_ok=True)
        self._load_registry()

    def _gemini_client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    # ------------------------------------------------------------------
    # Registry — maps original_file_path → json_tree_path
    # ------------------------------------------------------------------

    def _registry_path(self) -> Path:
        return self._index_dir / _REGISTRY_FILE

    def _load_registry(self) -> None:
        rp = self._registry_path()
        if rp.exists():
            try:
                self._registry = json.loads(rp.read_text(encoding="utf-8"))
            except Exception:
                self._registry = {}

    def _save_registry(self) -> None:
        self._registry_path().write_text(
            json.dumps(self._registry, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def _run_pageindex_sync(self, file_path: Path) -> Path:
        """Run PageIndex CLI synchronously. Called inside asyncio.to_thread()."""
        stem = file_path.stem
        out_path = self._index_dir / f"{stem}.json"

        # Try to import pageindex as a Python package first (preferred).
        try:
            from pageindex import PageIndex  # type: ignore[import]

            pi = PageIndex(
                pdf_path=str(file_path) if file_path.suffix.lower() == ".pdf" else None,
                md_path=str(file_path) if file_path.suffix.lower() in {".md", ".markdown"} else None,
                output_dir=str(self._index_dir),
                model=settings.gemini_llm_model,
            )
            pi.run()
        except ImportError:
            # Fall back to subprocess if pageindex isn't importable as a package.
            pageindex_bin = shutil.which("pageindex") or _find_pageindex_script()
            if pageindex_bin is None:
                raise RuntimeError(
                    "PageIndex is not installed. "
                    "Run: pip install git+https://github.com/VectifyAI/PageIndex.git"
                )
            suffix = file_path.suffix.lower()
            flag = "--pdf_path" if suffix == ".pdf" else "--md_path"
            subprocess.run(
                [sys.executable, pageindex_bin, flag, str(file_path),
                 "--output_dir", str(self._index_dir)],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "GEMINI_API_KEY": settings.gemini_api_key},
            )

        # PageIndex writes <stem>_index.json or similar — find it.
        candidates = list(self._index_dir.glob(f"{stem}*.json"))
        candidates = [c for c in candidates if c.name != _REGISTRY_FILE]
        if not candidates:
            raise FileNotFoundError(
                f"PageIndex did not produce an output JSON for {file_path}"
            )
        produced = max(candidates, key=lambda p: p.stat().st_mtime)
        if produced != out_path:
            produced.rename(out_path)
        return out_path

    async def index_document(self, file_path: Path) -> str:
        key = str(file_path)
        if key in self._registry:
            logger.info("PageIndex: already indexed %s, skipping", file_path.name)
            return self._registry[key]

        logger.info("PageIndex: indexing %s → %s", file_path.name, self._index_dir)
        out_path = await asyncio.to_thread(self._run_pageindex_sync, file_path)
        self._registry[key] = str(out_path)
        self._save_registry()
        logger.info("PageIndex: indexed %s → %s", file_path.name, out_path.name)
        return str(out_path)

    # ------------------------------------------------------------------
    # Query — Gemini navigates the tree, reads page text, answers
    # ------------------------------------------------------------------

    def _load_source_text_by_pages(self, file_path: Path, start_page: int, end_page: int) -> str:
        """Extract text from a page range of a PDF (1-indexed)."""
        if file_path.suffix.lower() != ".pdf":
            # For non-PDFs use the full text (small files)
            return file_path.read_text(encoding="utf-8", errors="ignore")
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        total = len(reader.pages)
        s = max(0, start_page - 1)
        e = min(total, end_page)
        return "\n".join((reader.pages[i].extract_text() or "") for i in range(s, e))

    def _navigate_tree_sync(
        self,
        tree: dict,
        question: str,
        source_file: Path,
        history_block: str,
        persona: str,
    ) -> tuple[str, list[dict]]:
        """Use Gemini to navigate a single document tree and answer the question."""
        # Step 1: ask Gemini which nodes to read (token-budgeted tree)
        tree_summary = json.dumps(self._compact_tree(tree), ensure_ascii=False, indent=2)
        tree_summary = truncate_to_tokens(
            tree_summary, settings.tree_nav_budget_tokens, label="pageindex tree"
        )
        nav_prompt = prompts.build_tree_nav_prompt(
            document_name=source_file.name,
            question=question,
            tree_json=tree_summary,
            history_block=history_block,
        )
        log_prompt_size("pageindex.nav", nav_prompt)
        nav_response = self._gemini_client().models.generate_content(
            model=settings.gemini_llm_model,
            contents=nav_prompt,
            config=_NAV_CONFIG,
        )
        try:
            nav_data = json.loads(nav_response.text or "{}")
            relevant_nodes = nav_data.get("relevant_nodes", [])
        except Exception:
            relevant_nodes = []

        if not relevant_nodes:
            return "", []

        # Step 2: read the actual page text for the top sections (capped)
        content_parts: list[str] = []
        page_map: dict[int, str] = {}  # page → section label, for citation enrichment
        for node in relevant_nodes[: settings.max_sections_per_doc]:
            start_p = node.get("start_page", 1)
            end_p = node.get("end_page", start_p + 1)
            text = self._load_source_text_by_pages(source_file, start_p, end_p)
            if text.strip():
                content_parts.append(f"[Trang {start_p}-{end_p}]\n{text.strip()}")
                page_map[start_p] = node.get("reason", "")

        if not content_parts:
            return "", []

        # Budget the combined excerpts: drop whole sections rather than slice (C1/C3).
        content = fit_sections(
            content_parts, settings.answer_content_budget_tokens, label="pageindex excerpts"
        )

        # Step 3: generate a grounded answer; citations come from the answer itself (B4)
        page_range = (
            f"trang {relevant_nodes[0].get('start_page', '?')}–"
            f"{relevant_nodes[-1].get('end_page', '?')}"
        )
        answer_prompt = prompts.build_answer_prompt(
            persona=persona,
            document_name=source_file.name,
            page_range=page_range,
            content=content,
            question=question,
            history_block=history_block,
        )
        log_prompt_size("pageindex.answer", answer_prompt)
        ans_response = self._gemini_client().models.generate_content(
            model=settings.gemini_llm_model,
            contents=answer_prompt,
            config=_ANSWER_CONFIG,
        )
        try:
            parsed = json.loads(ans_response.text or "{}")
        except Exception:
            return "", []

        answer_text = (parsed.get("answer") or "").strip()
        citations = [
            {
                "document": source_file.name,
                "page": c.get("page", 0),
                "section": c.get("section") or page_map.get(c.get("page", 0), ""),
                "domain": self._domain,
            }
            for c in parsed.get("citations", [])
            if c.get("page")
        ]
        return answer_text, citations

    def _compact_tree(self, node: dict, depth: int = 0) -> dict:
        """Strip large fields from the tree for the navigation prompt (C4)."""
        out: dict = {
            "node_id": node.get("node_id", ""),
            "title": node.get("title", ""),
            "start_index": node.get("start_index", 0),
            "end_index": node.get("end_index", 0),
        }
        if node.get("summary"):
            out["summary"] = node["summary"][: settings.tree_summary_char_cap]
        if node.get("nodes") and depth < settings.tree_max_depth:
            out["nodes"] = [self._compact_tree(c, depth + 1) for c in node["nodes"]]
        return out

    async def query(
        self,
        question: str,
        history: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> PageIndexResult:
        if not self._registry:
            return PageIndexResult(
                answer="Chưa có tài liệu nào được nạp cho lĩnh vực này.",
                citations=[],
            )

        # History is already pre-trimmed by the orchestrator — no second trim here.
        history_block = prompts.format_history(history)
        persona = system_prompt or prompts.DEFAULT_PAGEINDEX_PERSONA

        # Cap the number of trees we fan out to, to bound cost/context (C3).
        items = list(self._registry.items())[: settings.max_docs_per_synthesis]
        tasks = [
            asyncio.to_thread(
                self._query_one_sync,
                Path(json_path),
                Path(orig_path),
                question,
                history_block,
                persona,
            )
            for orig_path, json_path in items
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        answers: list[tuple[str, list[dict]]] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("PageIndex query error: %s", r)
                continue
            answer_text, cits = r
            if answer_text:
                answers.append((answer_text, cits))

        if not answers:
            return PageIndexResult(
                answer="Các tài liệu liên quan không chứa câu trả lời cho câu hỏi này.",
                citations=[],
            )

        if len(answers) == 1:
            return PageIndexResult(answer=answers[0][0], citations=answers[0][1])

        # Synthesize multiple answers (token-budgeted, language-driven — A2, C1)
        sections = [f"Tài liệu {i + 1}:\n{ans}" for i, (ans, _) in enumerate(answers)]
        answers_block = fit_sections(
            sections, settings.synthesis_input_budget_tokens, label="pageindex answers"
        )
        all_citations = [c for _, cits in answers for c in cits]
        synth_prompt = prompts.build_pageindex_synthesis_prompt(
            n=len(answers), answers_block=answers_block, question=question
        )
        log_prompt_size("pageindex.synthesize", synth_prompt)
        # Use asyncio.to_thread to avoid blocking the event loop with a sync SDK call.
        synth = await asyncio.to_thread(
            self._gemini_client().models.generate_content,
            model=settings.gemini_llm_model,
            contents=synth_prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return PageIndexResult(
            answer=(synth.text or answers[0][0]).strip(),
            citations=all_citations,
        )

    def _query_one_sync(
        self,
        json_path: Path,
        source_path: Path,
        question: str,
        history_block: str,
        persona: str,
    ) -> tuple[str, list[dict]]:
        if not json_path.exists():
            return "", []
        try:
            tree = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load index %s: %s", json_path, exc)
            return "", []
        return self._navigate_tree_sync(tree, question, source_path, history_block, persona)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        return len(self._registry) > 0

    def indexed_count(self) -> int:
        return len(self._registry)

    def list_indexed(self) -> list[str]:
        return list(self._registry.keys())


def _find_pageindex_script() -> str | None:
    """Try to locate the run_pageindex.py script on PATH or common locations."""
    candidates = [
        shutil.which("run_pageindex"),
        shutil.which("run_pageindex.py"),
        str(Path(sys.prefix) / "bin" / "run_pageindex.py"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None
