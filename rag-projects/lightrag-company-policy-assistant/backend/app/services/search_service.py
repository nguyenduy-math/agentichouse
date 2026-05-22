"""SearchService — navigates downloaded tree JSONs and answers questions via Gemini.

The tree JSONs were built by PageIndex Cloud and stored locally by PageIndexCloudService.
Each node carries a ``text`` field (structured summary), so no cloud calls are needed
at query time.

Per-document flow (3 steps):
  1. Navigate: compact tree → Gemini (TreeNavigation schema) → set of node_ids
  2. Collect:  gather node ``text`` for selected nodes + optional verbatim PDF page text
  3. Answer:   Gemini (GroundedAnswer schema) with budgeted content → answer + citations

Multiple documents are queried in parallel then synthesized into one answer.

The tree field for page numbers may be ``start_index``, ``page_index``, ``page``, or
``start_page`` depending on the PageIndex SDK version — _node_page() handles all forms.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from google import genai
from google.genai import types

from app import prompts
from app.config import settings
from app.context_budget import fit_sections, log_prompt_size, truncate_to_tokens
from app.schemas import GroundedAnswer, TreeNavigation

logger = logging.getLogger(__name__)

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


class SearchResult:
    def __init__(self, answer: str, citations: list[dict], documents: list[str]) -> None:
        self.answer = answer
        self.citations = citations   # list of {document, page, section}
        self.documents = documents


def _node_page(node: dict) -> int:
    """Return the starting page of a node, tolerating different SDK field names."""
    for key in ("start_index", "page_index", "page", "start_page"):
        val = node.get(key)
        if isinstance(val, int):
            return val
    return 0


def _node_page_range(node: dict) -> tuple[int, int]:
    """Return (start_page, end_page) for a node."""
    start = _node_page(node)
    end = start
    for key in ("end_index", "end_page"):
        val = node.get(key)
        if isinstance(val, int):
            end = val
            break
    return start, max(start, end)


def _load_pdf_pages(pdf_path: Path | None, start: int, end: int) -> str:
    """Extract verbatim text from PDF pages [start, end] (1-indexed).

    Returns "" on any error so callers can fall back to node.text gracefully.
    """
    if not pdf_path or not pdf_path.exists():
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        total = len(reader.pages)
        s = max(0, (start or 1) - 1)
        e = min(total, end or start or 1)
        return "\n".join((reader.pages[i].extract_text() or "") for i in range(s, e))
    except Exception as exc:
        logger.warning("Could not read PDF %s (pages %s-%s): %s", pdf_path, start, end, exc)
        return ""


class SearchService:
    """Navigates local tree JSONs and generates grounded answers via Gemini."""

    def __init__(self, tree_source) -> None:
        # tree_source: any object with .tree_paths() and .is_ready()
        self._tree_source = tree_source
        self._client: genai.Client | None = None

    def _gemini(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    # ------------------------------------------------------------------
    # Tree utilities
    # ------------------------------------------------------------------

    def _compact_node(self, node: dict, depth: int = 0) -> dict:
        """Strip large fields (text) from a node for the navigation prompt."""
        out: dict = {
            "node_id": node.get("node_id", ""),
            "title": node.get("title", ""),
            "page": _node_page(node),
        }
        summary = node.get("summary") or node.get("text")
        if summary:
            out["summary"] = summary[: settings.tree_summary_char_cap]
        children = node.get("nodes")
        if children and depth < settings.tree_max_depth:
            out["nodes"] = [self._compact_node(c, depth + 1) for c in children]
        return out

    def _compact_tree(self, tree: list | dict) -> list:
        roots = tree if isinstance(tree, list) else [tree]
        return [self._compact_node(n) for n in roots]

    def _collect_node_text(
        self, tree: list | dict, node_ids: set[str]
    ) -> list[tuple[str, int, int, str]]:
        """Walk tree and collect (title, start, end, text) for selected node_ids."""
        found: list[tuple[str, int, int, str]] = []

        def walk(node: dict) -> None:
            if node.get("node_id") in node_ids:
                text = (node.get("text") or "").strip()
                if text:
                    start, end = _node_page_range(node)
                    found.append((node.get("title", ""), start, end, text))
            for child in node.get("nodes", []) or []:
                walk(child)

        roots = tree if isinstance(tree, list) else [tree]
        for root in roots:
            walk(root)
        return found

    # ------------------------------------------------------------------
    # Single-document query
    # ------------------------------------------------------------------

    def _query_one_sync(
        self,
        filename: str,
        tree_path: Path,
        pdf_path: Path | None,
        question: str,
        history_block: str,
        persona: str,
    ) -> tuple[str, list[dict]]:
        if not tree_path.exists():
            return "", []
        try:
            tree = json.loads(tree_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load tree %s: %s", tree_path, exc)
            return "", []

        # Step 1: navigate compact tree → relevant node_ids
        tree_json = json.dumps(self._compact_tree(tree), ensure_ascii=False, indent=2)
        tree_json = truncate_to_tokens(
            tree_json, settings.tree_nav_budget_tokens, label="tree nav"
        )
        nav_prompt = prompts.build_tree_nav_prompt(
            document_name=filename,
            question=question,
            tree_json=tree_json,
            history_block=history_block,
        )
        log_prompt_size("search.nav", nav_prompt)
        nav_resp = self._gemini().models.generate_content(
            model=settings.gemini_llm_model, contents=nav_prompt, config=_NAV_CONFIG
        )
        try:
            nav_data = json.loads(nav_resp.text or "{}")
            relevant = nav_data.get("relevant_nodes", [])
        except Exception:
            relevant = []
        if not relevant:
            return "", []

        node_ids = {r.get("node_id") for r in relevant if r.get("node_id")}
        sections = self._collect_node_text(tree, node_ids)[: settings.max_sections_per_doc]
        if not sections:
            return "", []

        # Step 2: combine node text with optional verbatim PDF pages
        content_parts: list[str] = []
        for title, start, end, text in sections:
            page_label = f"Trang {start}" if start == end else f"Trang {start}-{end}"
            part = f"[Mục: {title or 'N/A'} · {page_label}]\n{text}"
            pdf_text = _load_pdf_pages(pdf_path, start, end) if pdf_path else ""
            if pdf_text.strip():
                part += f"\n\n[Trích nguyên văn từ PDF, {page_label}]\n{pdf_text.strip()}"
            content_parts.append(part)

        content = fit_sections(
            content_parts, settings.answer_content_budget_tokens, label="node+pdf"
        )
        page_map = {start: title for title, start, _, _ in sections}
        first_title = sections[0][0] or "?"
        last_title  = sections[-1][0] or "?"
        section_range = (
            first_title if first_title == last_title else f"{first_title} … {last_title}"
        )

        # Step 3: grounded answer with citations
        answer_prompt = prompts.build_answer_prompt(
            persona=persona,
            document_name=filename,
            section_range=section_range,
            content=content,
            question=question,
            history_block=history_block,
        )
        log_prompt_size("search.answer", answer_prompt)
        ans_resp = self._gemini().models.generate_content(
            model=settings.gemini_llm_model, contents=answer_prompt, config=_ANSWER_CONFIG
        )
        try:
            parsed = json.loads(ans_resp.text or "{}")
        except Exception:
            return "", []

        answer_text = (parsed.get("answer") or "").strip()
        citations = [
            {
                "document": filename,
                "page": c.get("page", 0),
                "section": c.get("section") or page_map.get(c.get("page", 0), ""),
            }
            for c in parsed.get("citations", [])
            if c.get("page")
        ]
        return answer_text, citations

    # ------------------------------------------------------------------
    # Multi-document fan-out + synthesis
    # ------------------------------------------------------------------

    async def query(
        self,
        question: str,
        history: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> SearchResult:
        paths = self._tree_source.tree_paths()
        if not paths:
            return SearchResult(prompts.NO_POLICY_DOMAIN_RESPONSE, [], [])

        history_block = prompts.format_history(history)
        persona = system_prompt or prompts.DEFAULT_PAGEINDEX_PERSONA

        paths = paths[: settings.max_docs_per_synthesis]
        tasks = [
            asyncio.to_thread(
                self._query_one_sync,
                filename, tree_path, pdf_path, question, history_block, persona,
            )
            for filename, tree_path, pdf_path in paths
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        answers: list[tuple[str, str, list[dict]]] = []
        for (filename, _, _), r in zip(paths, results):
            if isinstance(r, Exception):
                logger.warning("Search error for %s: %s", filename, r)
                continue
            answer_text, cits = r
            if answer_text:
                answers.append((filename, answer_text, cits))

        if not answers:
            return SearchResult(
                "Các tài liệu liên quan không chứa câu trả lời cho câu hỏi này.",
                [], [],
            )

        if len(answers) == 1:
            fn, ans, cits = answers[0]
            return SearchResult(ans, cits, [fn])

        # Synthesize multiple answers
        sections = [f"Tài liệu «{fn}»:\n{ans}" for fn, ans, _ in answers]
        answers_block = fit_sections(
            sections, settings.synthesis_input_budget_tokens, label="doc answers"
        )
        all_citations = [c for _, _, cits in answers for c in cits]
        docs = [fn for fn, _, _ in answers]
        synth_prompt = prompts.build_pageindex_synthesis_prompt(
            n=len(answers), answers_block=answers_block, question=question
        )
        log_prompt_size("search.synthesize", synth_prompt)
        synth = await asyncio.to_thread(
            self._gemini().models.generate_content,
            model=settings.gemini_llm_model,
            contents=synth_prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return SearchResult(
            answer=(synth.text or answers[0][1]).strip(),
            citations=all_citations,
            documents=docs,
        )
