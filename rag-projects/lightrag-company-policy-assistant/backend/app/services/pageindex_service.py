"""PageIndexService — manages PageIndex tree indices for one policy domain.

PageIndex (VectifyAI) converts PDFs/Markdown into hierarchical tree structures
(like a table of contents optimized for LLMs) and navigates them via reasoning
instead of vector similarity. This service wraps that workflow:

  1. index_document() — runs PageIndex CLI (via subprocess) to produce a JSON tree
  2. query()         — loads JSON trees + uses Gemini to navigate and answer

PageIndex is sync-heavy (LLM calls during indexing) so we wrap with
asyncio.to_thread() to avoid blocking the FastAPI event loop.

Installation:
    pip install git+https://github.com/VectifyAI/PageIndex.git
    (or clone the repo and install via: pip install -e .)
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

from app.config import settings

logger = logging.getLogger(__name__)

_REGISTRY_FILE = "registry.json"

_JSON_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    temperature=0.0,
)

_SYNTHESIS_PROMPT = """\
You are answering an employee question using content retrieved from company policy documents.

Below are answers from {n} different policy documents, each with page references.

{answers_block}

Employee question: {question}

Synthesize a single clear answer. Preserve all page references (e.g. "Page 4") from the source answers. If documents contradict each other, note the discrepancy. If the answer is not found in any document, say so clearly.
"""

_TREE_NAV_PROMPT = """\
You are navigating a company policy document index (table of contents) to find information relevant to an employee question.

Document: {document_name}
Question: {question}

Document index (JSON tree with section titles, summaries, and page ranges):
{tree_json}

Instructions:
1. Identify the most relevant sections for this question.
2. Return the node_ids and page ranges of sections to read.
3. If no sections are relevant, return an empty list.

Respond with JSON only:
{{
  "relevant_nodes": [
    {{"node_id": "0001", "start_page": 3, "end_page": 5, "reason": "why relevant"}}
  ]
}}
"""

_ANSWER_PROMPT = """\
You are a company policy specialist. Answer the employee question based only on the provided document excerpts. Cite page numbers where applicable (e.g. "According to page 4...").

Document: {document_name}
Relevant pages: {page_range}

Content:
{content}

Question: {question}

Answer (be precise and cite page numbers):
"""


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
        self, tree: dict, question: str, source_file: Path
    ) -> tuple[str, list[dict]]:
        """Use Gemini to navigate a single document tree and answer the question."""
        # Step 1: ask Gemini which nodes to read
        tree_summary = json.dumps(self._compact_tree(tree), ensure_ascii=False, indent=2)
        nav_prompt = _TREE_NAV_PROMPT.format(
            document_name=source_file.name,
            question=question,
            tree_json=tree_summary[:8000],  # cap to avoid token overflow
        )
        nav_response = self._gemini_client().models.generate_content(
            model=settings.gemini_llm_model,
            contents=nav_prompt,
            config=_JSON_CONFIG,
        )
        try:
            nav_data = json.loads(nav_response.text or "{}")
            relevant_nodes = nav_data.get("relevant_nodes", [])
        except Exception:
            relevant_nodes = []

        if not relevant_nodes:
            return "", []

        # Step 2: read the actual page text for relevant nodes
        citations: list[dict] = []
        content_parts: list[str] = []
        for node in relevant_nodes[:3]:  # limit to 3 sections per document
            start_p = node.get("start_page", 1)
            end_p = node.get("end_page", start_p + 1)
            text = self._load_source_text_by_pages(source_file, start_p, end_p)
            if text.strip():
                content_parts.append(f"[Pages {start_p}-{end_p}]\n{text.strip()}")
                citations.append({
                    "document": source_file.name,
                    "page": start_p,
                    "section": node.get("reason", ""),
                    "domain": self._domain,
                })

        if not content_parts:
            return "", []

        # Step 3: generate the answer
        page_range = f"pages {relevant_nodes[0].get('start_page', '?')}-{relevant_nodes[-1].get('end_page', '?')}"
        ans_response = self._gemini_client().models.generate_content(
            model=settings.gemini_llm_model,
            contents=_ANSWER_PROMPT.format(
                document_name=source_file.name,
                page_range=page_range,
                content="\n\n".join(content_parts)[:6000],
                question=question,
            ),
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return (ans_response.text or "").strip(), citations

    def _compact_tree(self, node: dict, depth: int = 0) -> dict:
        """Strip large fields from the tree for the navigation prompt."""
        out: dict = {
            "node_id": node.get("node_id", ""),
            "title": node.get("title", ""),
            "start_index": node.get("start_index", 0),
            "end_index": node.get("end_index", 0),
        }
        if node.get("summary"):
            out["summary"] = node["summary"][:200]
        if node.get("nodes") and depth < 3:
            out["nodes"] = [self._compact_tree(c, depth + 1) for c in node["nodes"]]
        return out

    async def query(self, question: str) -> PageIndexResult:
        if not self._registry:
            return PageIndexResult(
                answer="No documents have been indexed for this domain yet.",
                citations=[],
            )

        # Fan-out: query all indexed trees in parallel
        tasks = []
        for orig_path, json_path in self._registry.items():
            tasks.append(
                asyncio.to_thread(
                    self._query_one_sync,
                    Path(json_path),
                    Path(orig_path),
                    question,
                )
            )
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
                answer="The relevant documents did not contain an answer to this question.",
                citations=[],
            )

        if len(answers) == 1:
            return PageIndexResult(answer=answers[0][0], citations=answers[0][1])

        # Synthesize multiple answers
        answers_block = "\n\n".join(
            f"Document {i + 1}:\n{ans}" for i, (ans, _) in enumerate(answers)
        )
        all_citations = [c for _, cits in answers for c in cits]
        synth_prompt = _SYNTHESIS_PROMPT.format(
            n=len(answers),
            answers_block=answers_block[:8000],
            question=question,
        )
        synth = self._gemini_client().models.generate_content(
            model=settings.gemini_llm_model,
            contents=synth_prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return PageIndexResult(
            answer=(synth.text or answers[0][0]).strip(),
            citations=all_citations,
        )

    def _query_one_sync(
        self, json_path: Path, source_path: Path, question: str
    ) -> tuple[str, list[dict]]:
        if not json_path.exists():
            return "", []
        try:
            tree = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load index %s: %s", json_path, exc)
            return "", []
        return self._navigate_tree_sync(tree, question, source_path)

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
