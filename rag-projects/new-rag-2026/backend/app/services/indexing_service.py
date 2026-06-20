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

Log streaming: subprocess stdout is captured line-by-line into _log_lines.
SSE clients call stream_logs(offset) to get buffered lines + live updates.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Literal

logger = logging.getLogger(__name__)

IndexStatus = Literal["idle", "indexing", "importing", "ready", "error"]

# Sentinel prefix embedded in _log_lines to carry progress updates through the
# same SSE channel as log text.  stream_logs converts these to SSE progress events.
_PCT_PREFIX = "__pct__:"

# Known graphrag 2.x workflow names in execution order.
# Each completion moves the progress bar forward within the 5–68 % range.
_GRAPHRAG_WORKFLOWS = [
    "create_base_text_units",
    "create_base_extracted_entities",
    "create_summarized_entities",
    "create_base_entity_graph",
    "create_final_entities",
    "create_final_relationships",
    "create_final_community_reports",
    "create_final_text_units",
    "create_final_documents",
]

# Neo4j import milestone lines → percentage they represent (68–97 % range)
_NEO4J_MILESTONES: list[tuple[str, int]] = [
    ("Schema constraints", 70),
    ("Entities synced",    75),
    ("Relationships synced", 82),
    ("Communities imported",  87),
    ("Community membership",  90),
    ("Text units imported",   93),
    ("MENTIONS links",        96),
    ("Import complete",       98),
]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


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
        self._artifacts_dir = self._root / "output"
        self._neo4j_uri = neo4j_uri
        self._neo4j_user = neo4j_user
        self._neo4j_password = neo4j_password
        self._graphrag_service = graphrag_service
        self._graphrag_registry: dict[str, Any] = {}

        self._status: IndexStatus = "idle"
        self._message: str | None = None
        self._last_completed_at: str | None = None
        self._lock = asyncio.Lock()

        self._log_lines: list[str] = []
        self._log_event: asyncio.Event = asyncio.Event()

        self._pct: int = 0
        self._graphrag_completed: int = 0

    def set_graphrag_service(self, svc: Any) -> None:
        self._graphrag_service = svc

    def set_graphrag_registry(self, registry: dict[str, Any]) -> None:
        """Set the per-domain GraphRAGService registry so indexing can reload the right service."""
        self._graphrag_registry = registry

    def ensure_domain_workspace(self, domain_key: str) -> Path:
        """
        Create the per-domain workspace structure if it doesn't exist.

        Layout:
          graphrag_workspace/{domain_key}/
            settings.yaml   ← copy of base settings.yaml
            prompts/        ← symlink to graphrag_workspace/prompts/
            input/          ← where domain documents are stored
            logs/
        """
        workspace = self._root / domain_key
        (workspace / "input").mkdir(parents=True, exist_ok=True)
        (workspace / "logs").mkdir(exist_ok=True)

        # Copy base settings.yaml if not already present
        settings_dst = workspace / "settings.yaml"
        if not settings_dst.exists():
            settings_src = self._root / "settings.yaml"
            if settings_src.exists():
                settings_dst.write_text(settings_src.read_text(encoding="utf-8"), encoding="utf-8")
                logger.info("Copied settings.yaml to domain workspace: %s", workspace)

        # Symlink prompts/ → base prompts directory
        prompts_link = workspace / "prompts"
        if not prompts_link.exists():
            base_prompts = (self._root / "prompts").resolve()
            if base_prompts.exists():
                prompts_link.symlink_to(base_prompts, target_is_directory=True)
                logger.info("Created prompts symlink in: %s", workspace)

        return workspace

    # ── Log buffer ─────────────────────────────────────────────────────────────

    def _append_log(self, line: str) -> None:
        """Append a line to the buffer and wake up any SSE subscribers."""
        self._log_lines.append(line)
        self._log_event.set()

    def _clear_logs(self) -> None:
        self._log_lines.clear()
        self._log_event.clear()
        self._pct = 0
        self._graphrag_completed = 0

    def _update_progress(self, pct: int) -> None:
        """Clamp pct to [0, 100], advance only forward, then inject a sentinel."""
        pct = max(0, min(100, pct))
        if pct <= self._pct:
            return
        self._pct = pct
        # Inject a sentinel line so stream_logs can emit an SSE progress event
        self._log_lines.append(f"{_PCT_PREFIX}{pct}")
        self._log_event.set()

    def _parse_graphrag_progress(self, line: str) -> None:
        """
        Try to extract progress information from a graphrag output line.

        Strategy (first match wins):
          1. Known workflow completion   → advance by one workflow step (5–68 %)
          2. "Running workflow: X"       → set to the start of that workflow's slot
          3. Bare percentage "N %"       → scale into the graphrag phase (5–68 %)
        """
        clean = _ANSI_RE.sub("", line)  # strip ANSI escape codes

        # 1. Workflow completion
        low = clean.lower()
        if "complete" in low or "✅" in clean:
            for wf in _GRAPHRAG_WORKFLOWS:
                if wf in clean:
                    self._graphrag_completed += 1
                    pct = 5 + int(self._graphrag_completed / len(_GRAPHRAG_WORKFLOWS) * 63)
                    self._update_progress(pct)
                    return

        # 2. Workflow start
        if "running workflow" in low or "workflow" in low:
            for i, wf in enumerate(_GRAPHRAG_WORKFLOWS):
                if wf in clean:
                    pct = 5 + int(i / len(_GRAPHRAG_WORKFLOWS) * 63)
                    self._update_progress(pct)
                    return

        # 3. Bare percentage like "45%" or "45 %"
        m = re.search(r"(\d{1,3})\s*%", clean)
        if m:
            raw = int(m.group(1))
            pct = 5 + int(raw * 63 / 100)
            self._update_progress(pct)

    def _parse_neo4j_progress(self, line: str) -> None:
        """Map known import_to_neo4j.py output lines to progress values (68–98 %)."""
        for marker, pct in _NEO4J_MILESTONES:
            if marker.lower() in line.lower():
                self._update_progress(pct)
                return

    async def stream_logs(self, offset: int = 0) -> AsyncGenerator[str, None]:
        """
        Async generator yielding SSE-formatted chunks.

        Sends all buffered lines from `offset` immediately, then blocks waiting
        for new lines. Closes with a named 'done' event when the pipeline
        reaches a terminal state (ready / error).
        SSE clients that reconnect after navigating away pass their last-seen
        offset so they only receive the lines they missed.
        """
        cursor = offset
        while True:
            # Drain all available entries without holding any lock.
            # Progress sentinels are emitted as named SSE events so the browser
            # can distinguish them from plain log text.
            while cursor < len(self._log_lines):
                entry = self._log_lines[cursor]
                cursor += 1
                if entry.startswith(_PCT_PREFIX):
                    yield f"event: progress\ndata: {entry[len(_PCT_PREFIX):]}\n\n"
                else:
                    yield f"data: {entry}\n\n"

            # Terminal: pipeline finished and we've sent every line
            if self._status in ("ready", "error") and cursor >= len(self._log_lines):
                yield f"event: done\ndata: {self._status}\n\n"
                break

            # No pipeline running and nothing new to send
            if self._status == "idle" and cursor >= len(self._log_lines):
                yield "event: done\ndata: idle\n\n"
                break

            # Clear the event *before* re-checking to avoid the race where a
            # new line arrives between the drain loop and the wait below.
            self._log_event.clear()
            if cursor < len(self._log_lines):
                # A line arrived in the window between clear and this check
                continue

            try:
                await asyncio.wait_for(self._log_event.wait(), timeout=20.0)
            except asyncio.TimeoutError:
                # Send a SSE comment to keep the TCP connection alive through
                # proxies that close idle connections.
                yield ": keepalive\n\n"

    @property
    def status(self) -> IndexStatus:
        return self._status

    @property
    def message(self) -> str | None:
        return self._message

    @property
    def last_completed_at(self) -> str | None:
        return self._last_completed_at

    def prepare_for_graphrag(self, file_path: Path, domain_key: str) -> list[Path]:
        """
        Convert a document to one or more plain-text files in the domain's input directory.
        Each output file contains one article/section (≤ 2800 chars).

        Returns list of written .txt file paths.
        """
        from app.utils.document_parser import parse_document
        from app.utils.text_splitter import split_by_article

        workspace = self.ensure_domain_workspace(domain_key)
        input_dir = workspace / "input"

        pages = parse_document(str(file_path))
        all_text = "\n\n".join(p["text"] for p in pages)

        articles = split_by_article(all_text, max_chunk_size=2800)

        output_paths: list[Path] = []
        stem = file_path.stem
        for i, article_text in enumerate(articles):
            out = input_dir / f"{stem}_part{i:04d}.txt"
            out.write_text(article_text, encoding="utf-8")
            output_paths.append(out)

        logger.info(
            "Prepared %d chunks from '%s' → domain '%s'",
            len(output_paths), file_path.name, domain_key,
        )
        return output_paths

    async def start_indexing(self, domain_key: str, reimport: bool = False) -> bool:
        """
        Start the full indexing pipeline for a specific domain asynchronously.

        Returns True if started, False if already running.
        """
        async with self._lock:
            if self._status in ("indexing", "importing"):
                return False
            self._status = "indexing"
            self._message = f"GraphRAG indexing started for domain '{domain_key}'"

        asyncio.create_task(self._run_pipeline(domain_key=domain_key, reimport=reimport))
        return True

    async def _run_pipeline(self, domain_key: str, reimport: bool = False) -> None:
        """Full pipeline: graphrag index → import_to_neo4j → reload (per domain)."""
        workspace = self.ensure_domain_workspace(domain_key)
        artifacts_dir = workspace / "output"

        self._clear_logs()
        self._update_progress(1)
        self._append_log(
            f"[pipeline] Started for domain '{domain_key}' at "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        try:
            # Step 1: graphrag index
            self._update_progress(3)
            self._append_log(f"[pipeline] Step 1/3 — running graphrag index (domain: {domain_key})...")
            logger.info("Starting graphrag index for domain '%s'...", domain_key)
            await self._run_graphrag_index(workspace)

            # Step 2: import_to_neo4j.py
            self._status = "importing"
            self._message = f"Importing artifacts to Neo4j (domain: {domain_key})..."
            self._update_progress(68)
            self._append_log("[pipeline] Step 2/3 — importing artifacts to Neo4j...")
            logger.info("Starting Neo4j import for domain '%s'...", domain_key)
            await self._run_neo4j_import(artifacts_dir)

            # Step 3: reload the domain-specific GraphRAG service
            self._update_progress(98)
            self._append_log("[pipeline] Step 3/3 — reloading search engines...")
            registry = getattr(self, "_graphrag_registry", None)
            if registry and domain_key in registry:
                logger.info("Reloading GraphRAG service for domain '%s'...", domain_key)
                await registry[domain_key].reload()
            elif self._graphrag_service is not None:
                await self._graphrag_service.reload()

            self._status = "ready"
            self._message = f"Indexing complete for domain '{domain_key}'"
            self._last_completed_at = datetime.now(timezone.utc).isoformat()
            self._update_progress(100)
            self._append_log(f"[pipeline] Done — domain '{domain_key}' knowledge graph is ready.")
            logger.info("Indexing pipeline complete for domain '%s'.", domain_key)

        except Exception as exc:
            self._status = "error"
            self._message = f"Pipeline error: {exc}"
            self._append_log(f"[pipeline] ERROR: {exc}")
            logger.error("Indexing pipeline failed for domain '%s': %s", domain_key, exc, exc_info=True)

    def _graphrag_bin(self) -> str:
        """
        Resolve the graphrag CLI binary, trying candidates in order:
          1. Next to sys.executable — correct when venv is activated or inside Docker.
          2. shutil.which("graphrag") — correct when graphrag is on PATH.
          3. Project .venv/bin/graphrag — correct for local dev without activating the venv.
        """
        import shutil

        candidates = [
            Path(sys.executable).parent / "graphrag",
            Path(__file__).parent.parent.parent / ".venv" / "bin" / "graphrag",
        ]
        for path in candidates:
            if path.exists():
                return str(path)

        on_path = shutil.which("graphrag")
        if on_path:
            return on_path

        raise RuntimeError(
            "graphrag binary not found. "
            "Run: pip install 'graphrag>=2.0.0,<3.0.0'"
        )

    def _subprocess_env(self) -> dict:
        """
        Build the environment for graphrag/import subprocesses.

        pydantic-settings loads .env into the Settings object but does NOT write
        to os.environ, so subprocesses would inherit an empty GEMINI_API_KEY.
        We merge os.environ with the values from Settings to cover both cases:
          - user exported vars in the shell (already in os.environ)
          - user relies on .env only (only in settings, not os.environ)
        """
        from app.config import settings
        env = dict(os.environ)
        overrides = {
            "GEMINI_API_KEY":      settings.GEMINI_API_KEY,
            "OPENAI_API_KEY":      settings.OPENAI_API_KEY,
            "NEO4J_URI":           settings.NEO4J_URI,
            "NEO4J_USER":          settings.NEO4J_USER,
            "NEO4J_PASSWORD":      settings.NEO4J_PASSWORD,
            "GRAPHRAG_QUERY_MODEL": settings.GRAPHRAG_QUERY_MODEL,
            "EMBEDDING_MODEL":     settings.EMBEDDING_MODEL,
        }
        env.update({k: v for k, v in overrides.items() if v})
        return env

    async def _run_graphrag_index(self, workspace: Path) -> None:
        """Run `graphrag index` in the given domain workspace, streaming output into the log buffer."""
        cmd = [
            self._graphrag_bin(),
            "index",
            "--root", str(workspace),
        ]
        input_dir = workspace / "input"
        txt_files = list(input_dir.glob("*.txt")) if input_dir.exists() else []
        self._append_log(f"[graphrag] Input files: {len(txt_files)} chunks in {input_dir}")
        self._append_log(f"[graphrag] $ {' '.join(cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=self._subprocess_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        tail: list[str] = []
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if line:
                self._append_log(f"[graphrag] {line}")
                self._parse_graphrag_progress(line)
                tail.append(line)
                if len(tail) > 100:
                    tail.pop(0)
        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                f"graphrag index failed (exit {proc.returncode}):\n" + "\n".join(tail[-50:])
            )
        logger.info("graphrag index completed successfully.")

    async def _run_neo4j_import(self, artifacts_dir: Path) -> None:
        """Run import_to_neo4j.py for a specific domain artifacts directory."""
        script = Path(__file__).parent.parent.parent / "scripts" / "import_to_neo4j.py"
        python_bin = str(Path(self._graphrag_bin()).parent / "python")
        cmd = [
            python_bin, str(script),
            "--artifacts", str(artifacts_dir),
            "--uri", self._neo4j_uri,
            "--user", self._neo4j_user,
            "--password", self._neo4j_password,
        ]
        # Build a display version of the command with the password redacted
        cmd_display = cmd[:]
        pw_idx = cmd_display.index("--password") + 1
        cmd_display[pw_idx] = "***"
        self._append_log(f"[neo4j] $ {' '.join(cmd_display)}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=self._subprocess_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        tail: list[str] = []
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if line:
                self._append_log(f"[neo4j] {line}")
                self._parse_neo4j_progress(line)
                tail.append(line)
                if len(tail) > 100:
                    tail.pop(0)
        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                f"import_to_neo4j.py failed (exit {proc.returncode}):\n" + "\n".join(tail[-50:])
            )
        logger.info("Neo4j import completed successfully.")
