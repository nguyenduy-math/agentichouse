"""
Document indexing service.

Pipeline:
  1. Parse uploaded document (PDF/DOCX/TXT) via document_parser
  2. Split into article-sized chunks via text_splitter
  3. Write chunks to graphrag_workspace/input/ as .txt files
  4. Trigger `graphrag index` subprocess
  5. On success, trigger import_to_neo4j.py subprocess
  6. Notify GraphRAGService to reload search engines

State machine: idle → indexing → importing → ready | error
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

IndexStatus = Literal["idle", "indexing", "importing", "ready", "error"]


class IndexingService:
    """
    Manages the full indexing pipeline from document upload to Neo4j import.
    Thread-safe via asyncio.Lock().
    """

    def __init__(
        self,
        graphrag_root: str,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        graphrag_service: Any | None = None,
    ) -> None:
        self._root = Path(graphrag_root)
        self._input_dir = self._root / "input"
        self._artifacts_dir = self._root / "output" / "artifacts"
        self._neo4j_uri = neo4j_uri
        self._neo4j_user = neo4j_user
        self._neo4j_password = neo4j_password
        self._graphrag_service = graphrag_service

        self._status: IndexStatus = "idle"
        self._message: str | None = None
        self._last_completed_at: str | None = None
        self._lock = asyncio.Lock()

    # Import Any here to avoid circular at module level
    def set_graphrag_service(self, svc: Any) -> None:
        self._graphrag_service = svc

    @property
    def status(self) -> IndexStatus:
        return self._status

    @property
    def message(self) -> str | None:
        return self._message

    @property
    def last_completed_at(self) -> str | None:
        return self._last_completed_at

    def prepare_for_graphrag(self, file_path: Path) -> list[Path]:
        """
        Convert a document to one or more plain-text files for GraphRAG input.
        Each output file contains one article/section (≤ 2800 chars).

        Returns list of written .txt file paths.
        """
        from app.utils.document_parser import parse_document
        from app.utils.text_splitter import split_by_article

        pages = parse_document(str(file_path))
        all_text = "\n\n".join(p["text"] for p in pages)

        articles = split_by_article(all_text, max_chunk_size=2800)

        self._input_dir.mkdir(parents=True, exist_ok=True)
        output_paths: list[Path] = []
        stem = file_path.stem
        for i, article_text in enumerate(articles):
            out = self._input_dir / f"{stem}_part{i:04d}.txt"
            out.write_text(article_text, encoding="utf-8")
            output_paths.append(out)

        logger.info("Prepared %d chunks from '%s'", len(output_paths), file_path.name)
        return output_paths

    async def start_indexing(self, reimport: bool = False) -> bool:
        """
        Start the full indexing pipeline asynchronously.

        Returns True if started, False if already running.
        """
        async with self._lock:
            if self._status in ("indexing", "importing"):
                return False
            self._status = "indexing"
            self._message = "GraphRAG indexing started"

        asyncio.create_task(self._run_pipeline(reimport=reimport))
        return True

    async def _run_pipeline(self, reimport: bool = False) -> None:
        """Full pipeline: graphrag index → import_to_neo4j → reload."""
        try:
            # Step 1: graphrag index
            logger.info("Starting graphrag index...")
            await self._run_graphrag_index()

            # Step 2: import_to_neo4j.py
            self._status = "importing"
            self._message = "Importing artifacts to Neo4j..."
            logger.info("Starting Neo4j import...")
            await self._run_neo4j_import()

            # Step 3: reload GraphRAG search engines
            if self._graphrag_service is not None:
                logger.info("Reloading GraphRAG search engines...")
                await self._graphrag_service.reload()

            self._status = "ready"
            self._message = "Indexing and import complete"
            self._last_completed_at = datetime.now(timezone.utc).isoformat()
            logger.info("Indexing pipeline complete.")

        except Exception as exc:
            self._status = "error"
            self._message = f"Pipeline error: {exc}"
            logger.error("Indexing pipeline failed: %s", exc, exc_info=True)

    async def _run_graphrag_index(self) -> None:
        """Run `graphrag index` as a subprocess."""
        cmd = [
            sys.executable, "-m", "graphrag.index",
            "--root", str(self._root),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            output = stdout.decode(errors="replace") if stdout else ""
            raise RuntimeError(f"graphrag index failed (exit {proc.returncode}):\n{output[-2000:]}")
        logger.info("graphrag index completed successfully.")

    async def _run_neo4j_import(self) -> None:
        """Run import_to_neo4j.py as a subprocess."""
        script = Path(__file__).parent.parent.parent / "scripts" / "import_to_neo4j.py"
        cmd = [
            sys.executable, str(script),
            "--artifacts", str(self._artifacts_dir),
            "--uri", self._neo4j_uri,
            "--user", self._neo4j_user,
            "--password", self._neo4j_password,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            output = stdout.decode(errors="replace") if stdout else ""
            raise RuntimeError(f"import_to_neo4j.py failed (exit {proc.returncode}):\n{output[-2000:]}")
        logger.info("Neo4j import completed successfully.")


# Forward reference for type hints
from typing import Any  # noqa: E402
