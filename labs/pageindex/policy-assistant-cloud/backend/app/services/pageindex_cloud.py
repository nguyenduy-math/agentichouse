"""PageIndexCloudService — xây cây tri thức trên PageIndex Cloud, tải về JSON.

Luồng:
  1. submit_document(pdf) → doc_id  (PageIndex Cloud xử lý PDF, dựng cây)
  2. poll get_document/get_tree cho tới khi status == "completed"
  3. get_tree(doc_id) → lưu phần "result" thành tree_storage/{doc_id}.json
  4. ghi sổ đăng ký registry.json: doc_id → {filename, tree_path, node_count}

SDK PageIndex là đồng bộ (gọi HTTP), nên hàm ingest() bọc trong asyncio.to_thread
để không chặn vòng lặp sự kiện của FastAPI.

Cài đặt: pip install -U pageindex
Lấy API key: https://dash.pageindex.ai/api-keys
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from pageindex import PageIndexClient

logger = logging.getLogger(__name__)

_REGISTRY_FILE = "registry.json"


def _count_nodes(nodes: list[dict] | dict | None) -> int:
    """Đếm tổng số node trong cây (đệ quy)."""
    if nodes is None:
        return 0
    if isinstance(nodes, dict):
        nodes = [nodes]
    total = 0
    for n in nodes:
        total += 1 + _count_nodes(n.get("nodes"))
    return total


def _extract_doc_id(result: dict | str) -> str:
    """submit_document có thể trả về {'doc_id': ...} hoặc chuỗi doc_id trực tiếp."""
    if isinstance(result, str):
        return result
    return result.get("doc_id") or result.get("id") or ""


class PageIndexCloudService:
    def __init__(self, api_key: str, tree_dir: Path, poll_interval: int = 3,
                 poll_timeout: int = 300) -> None:
        self._client = PageIndexClient(api_key=api_key)
        self._tree_dir = tree_dir
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout
        self._registry: dict[str, dict] = {}  # doc_id → {filename, tree_path, node_count}
        tree_dir.mkdir(parents=True, exist_ok=True)
        self._load_registry()

    # ------------------------------------------------------------------
    # Sổ đăng ký
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
    # Cloud: submit → poll → download
    # ------------------------------------------------------------------

    def _status_of(self, doc_id: str) -> str:
        """Lấy trạng thái xử lý của tài liệu, chịu được khác biệt giữa các phiên bản SDK."""
        # Ưu tiên get_document; nếu không có thì rơi về get_tree.
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

    def _submit_and_wait(self, pdf_path: Path) -> str:
        result = self._client.submit_document(str(pdf_path))
        doc_id = _extract_doc_id(result)
        if not doc_id:
            raise RuntimeError(f"PageIndex không trả về doc_id cho {pdf_path.name}: {result!r}")

        deadline = time.monotonic() + self._poll_timeout
        while True:
            status = self._status_of(doc_id)
            if status == "completed":
                return doc_id
            if status in {"failed", "error"}:
                raise RuntimeError(f"PageIndex xử lý thất bại cho {pdf_path.name} (status={status})")
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"PageIndex chưa xử lý xong {pdf_path.name} sau {self._poll_timeout}s "
                    f"(status cuối: {status or 'unknown'})"
                )
            logger.info("PageIndex: đang xử lý %s (status=%s)…", pdf_path.name, status or "?")
            time.sleep(self._poll_interval)

    def _download_tree(self, doc_id: str, filename: str, pdf_path: str | None = None) -> dict:
        resp = self._client.get_tree(doc_id, node_summary=True)
        # get_tree trả về {'status', 'doc_id', 'result': [...]} — lấy "result".
        result = resp.get("result") if isinstance(resp, dict) else resp
        if not result:
            raise RuntimeError(f"PageIndex get_tree không có 'result' cho doc_id={doc_id}")

        tree_path = self._tree_dir / f"{doc_id}.json"
        tree_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        node_count = _count_nodes(result)
        entry = {
            "filename": filename,
            "tree_path": str(tree_path),
            "pdf_path": pdf_path,  # giữ đường dẫn PDF gốc để trích nguyên văn khi trả lời
            "node_count": node_count,
        }
        self._registry[doc_id] = entry
        self._save_registry()
        logger.info("PageIndex: đã tải cây %s → %s (%d node)", filename, tree_path.name, node_count)
        return entry

    def _ingest_sync(self, pdf_path: Path) -> dict:
        logger.info("PageIndex: nộp %s lên cloud…", pdf_path.name)
        doc_id = self._submit_and_wait(pdf_path)
        entry = self._download_tree(doc_id, pdf_path.name, str(pdf_path))
        return {"doc_id": doc_id, **entry, "status": "completed"}

    async def ingest(self, pdf_path: Path) -> dict:
        """Nộp PDF, chờ xử lý, tải cây về (không chặn event loop)."""
        return await asyncio.to_thread(self._ingest_sync, pdf_path)

    # ------------------------------------------------------------------
    # Tra cứu / quản lý
    # ------------------------------------------------------------------

    def list_docs(self) -> list[dict]:
        return [
            {"doc_id": doc_id, "filename": e.get("filename", ""),
             "node_count": e.get("node_count", 0)}
            for doc_id, e in self._registry.items()
        ]

    def tree_paths(self) -> list[tuple[str, Path, Path | None]]:
        """Trả về (filename, tree_path, pdf_path|None) cho mọi tài liệu đã nạp."""
        out: list[tuple[str, Path, Path | None]] = []
        for doc_id, e in self._registry.items():
            if not e.get("tree_path"):
                continue
            pdf = e.get("pdf_path")
            out.append(
                (e.get("filename", doc_id), Path(e["tree_path"]), Path(pdf) if pdf else None)
            )
        return out

    async def delete(self, doc_id: str) -> bool:
        entry = self._registry.pop(doc_id, None)
        if entry is None:
            return False
        # Xoá file JSON cục bộ
        tp = entry.get("tree_path")
        if tp and Path(tp).exists():
            try:
                Path(tp).unlink()
            except OSError:
                pass
        # Cố gắng xoá trên cloud (không bắt buộc thành công)
        try:
            await asyncio.to_thread(self._client.delete_document, doc_id)
        except Exception as exc:
            logger.warning("Không xoá được tài liệu trên cloud %s: %s", doc_id, exc)
        self._save_registry()
        return True

    def is_ready(self) -> bool:
        return len(self._registry) > 0

    def indexed_count(self) -> int:
        return len(self._registry)
