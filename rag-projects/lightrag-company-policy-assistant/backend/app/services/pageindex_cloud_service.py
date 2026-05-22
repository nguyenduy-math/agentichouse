"""PageIndexCloudService — uploads documents to PageIndex Cloud and stores trees locally.

Flow:
  1. submit_document(pdf) → doc_id   (PageIndex Cloud processes the PDF, builds a tree)
  2. poll get_document / get_tree until status == "completed"
  3. get_tree(doc_id, node_summary=True) → save resp["result"] as tree_dir/{doc_id}.json
  4. write registry.json: doc_id → {filename, tree_path, pdf_path, node_count}

The tree JSON is stored locally so SearchService can navigate it via Gemini without
making further cloud calls per query.

Installation: pip install -U pageindex
API key:       https://dash.pageindex.ai/api-keys
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_REGISTRY_FILE = "registry.json"
_POLL_INTERVAL_S = 3
_POLL_TIMEOUT_S  = 300


def _count_nodes(nodes: list | dict | None) -> int:
    """Recursively count all nodes in a tree."""
    if nodes is None:
        return 0
    if isinstance(nodes, dict):
        nodes = [nodes]
    total = 0
    for n in nodes:
        total += 1 + _count_nodes(n.get("nodes"))
    return total


def _extract_doc_id(result: dict | str) -> str:
    """submit_document may return {'doc_id': ...} or a bare doc_id string."""
    if isinstance(result, str):
        return result
    return result.get("doc_id") or result.get("id") or ""


class PageIndexCloudService:
    """Uploads PDFs/Markdown to PageIndex Cloud and keeps downloaded tree JSONs locally."""

    def __init__(self, api_key: str, tree_dir: Path,
                 poll_interval: int = _POLL_INTERVAL_S,
                 poll_timeout: int = _POLL_TIMEOUT_S) -> None:
        from pageindex import PageIndexClient  # type: ignore[import]
        self._client = PageIndexClient(api_key=api_key)
        self._tree_dir = tree_dir
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout
        self._registry: dict[str, dict] = {}  # doc_id → {filename, tree_path, pdf_path, node_count}
        tree_dir.mkdir(parents=True, exist_ok=True)
        self._load_registry()

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def _registry_path(self) -> Path:
        return self._tree_dir / _REGISTRY_FILE

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
    # Cloud: submit → poll → download tree
    # ------------------------------------------------------------------

    def _status_of(self, doc_id: str) -> str:
        """Get processing status, tolerating SDK version differences."""
        try:
            doc = self._client.get_document(doc_id)
            status = doc.get("status") if isinstance(doc, dict) else None
            if status:
                return status
        except Exception:
            pass
        try:
            tree = self._client.get_tree(doc_id)
            if isinstance(tree, dict):
                return tree.get("status", "")
        except Exception:
            pass
        return ""

    def _submit_and_wait(self, file_path: Path) -> str:
        result = self._client.submit_document(str(file_path))
        doc_id = _extract_doc_id(result)
        if not doc_id:
            raise RuntimeError(
                f"PageIndex did not return a doc_id for {file_path.name}: {result!r}"
            )
        deadline = time.monotonic() + self._poll_timeout
        while True:
            status = self._status_of(doc_id)
            if status == "completed":
                return doc_id
            if status in {"failed", "error"}:
                raise RuntimeError(
                    f"PageIndex processing failed for {file_path.name} (status={status})"
                )
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"PageIndex timed out after {self._poll_timeout}s "
                    f"for {file_path.name} (last status: {status or 'unknown'})"
                )
            logger.info("PageIndex cloud: processing %s (status=%s)…", file_path.name, status or "?")
            time.sleep(self._poll_interval)

    def _download_tree(self, doc_id: str, filename: str, pdf_path: str | None = None) -> dict:
        resp = self._client.get_tree(doc_id, node_summary=True)
        result = resp.get("result") if isinstance(resp, dict) else resp
        if not result:
            raise RuntimeError(
                f"PageIndex get_tree returned no 'result' for doc_id={doc_id}"
            )
        tree_path = self._tree_dir / f"{doc_id}.json"
        tree_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        node_count = _count_nodes(result)
        entry = {
            "filename": filename,
            "tree_path": str(tree_path),
            "pdf_path": pdf_path,
            "node_count": node_count,
        }
        self._registry[doc_id] = entry
        self._save_registry()
        logger.info(
            "PageIndex cloud: tree downloaded %s → %s (%d nodes)",
            filename, tree_path.name, node_count,
        )
        return entry

    def _ingest_sync(self, file_path: Path) -> dict:
        logger.info("PageIndex cloud: submitting %s…", file_path.name)
        doc_id = self._submit_and_wait(file_path)
        entry = self._download_tree(doc_id, file_path.name, str(file_path))
        return {"doc_id": doc_id, **entry, "status": "completed"}

    async def index_document(self, file_path: Path) -> None:
        """Upload file, wait for cloud processing, and download the tree JSON."""
        # Skip if a doc with this filename is already registered.
        already = {e.get("filename") for e in self._registry.values()}
        if file_path.name in already:
            logger.info("PageIndex cloud: %s already indexed, skipping", file_path.name)
            return
        await asyncio.to_thread(self._ingest_sync, file_path)

    # ------------------------------------------------------------------
    # Tree access (used by SearchService)
    # ------------------------------------------------------------------

    def tree_paths(self) -> list[tuple[str, Path, Path | None]]:
        """Return (filename, tree_path, pdf_path|None) for every registered document."""
        out: list[tuple[str, Path, Path | None]] = []
        for entry in self._registry.values():
            tp = entry.get("tree_path")
            if not tp:
                continue
            pdf = entry.get("pdf_path")
            out.append(
                (entry.get("filename", ""), Path(tp), Path(pdf) if pdf else None)
            )
        return out

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        return len(self._registry) > 0

    def indexed_count(self) -> int:
        return len(self._registry)

    def list_indexed(self) -> list[str]:
        return [e.get("filename", doc_id) for doc_id, e in self._registry.items()]
