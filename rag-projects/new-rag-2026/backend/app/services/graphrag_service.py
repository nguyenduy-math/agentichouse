"""
GraphRAG query service wrapping Microsoft GraphRAG 2.x LocalSearch and GlobalSearch.

Uses graphrag.api high-level functions with Parquet artifacts loaded from the
configured output directory (graphrag_workspace/output/).

Option A (native Neo4j storage) is available when ready — swap the output block
in settings.yaml. For now we use the file-based Parquet output (Option B).
"""
from __future__ import annotations

import asyncio
import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SearchMode(str, Enum):
    LOCAL = "local"
    GLOBAL = "global"


class GraphRAGService:
    """
    Wraps Microsoft GraphRAG 2.x LocalSearch and GlobalSearch via graphrag.api.

    DataFrames are loaded from Parquet at reload() time and cached in memory.
    Each search call passes the cached DataFrames to graphrag.api, which handles
    model instantiation internally (models are cached by ModelManager).

    Thread safety: asyncio.Lock() guards the reload path.
    """

    def __init__(self, workspace_root: str, neo4j_store: Any) -> None:
        self._root = Path(workspace_root)
        self._lock = asyncio.Lock()
        self._config: Any = None
        self._dfs: dict[str, Any] = {}
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    async def search(self, question: str, mode: SearchMode) -> dict[str, Any]:
        if not self._ready:
            logger.warning("GraphRAG not ready — no artifacts loaded.")
            return {"reply": "", "sources": []}

        try:
            import graphrag.api as api  # already on path after reload()

            if mode == SearchMode.LOCAL:
                result, context = await api.local_search(
                    config=self._config,
                    entities=self._dfs["entities"],
                    communities=self._dfs["communities"],
                    community_reports=self._dfs["community_reports"],
                    text_units=self._dfs["text_units"],
                    relationships=self._dfs["relationships"],
                    covariates=self._dfs.get("covariates"),
                    community_level=2,
                    response_type="multiple paragraphs",
                    query=question,
                )
            else:
                result, context = await api.global_search(
                    config=self._config,
                    entities=self._dfs["entities"],
                    communities=self._dfs["communities"],
                    community_reports=self._dfs["community_reports"],
                    community_level=None,
                    dynamic_community_selection=False,
                    response_type="multiple paragraphs",
                    query=question,
                )

            reply = result if isinstance(result, str) else str(result)
            return {
                "reply": reply,
                "sources": self._extract_sources(context),
            }

        except Exception as exc:
            logger.error("GraphRAG search error: %s", exc)
            return {"reply": "", "sources": []}

    async def reload(self) -> None:
        """
        (Re)load DataFrames from Parquet artifacts and config from settings.yaml.
        Called after indexing + Neo4j import completes.
        Thread-safe via asyncio.Lock().
        """
        async with self._lock:
            try:
                config, dfs = await asyncio.to_thread(self._load_artifacts)
                self._config = config
                self._dfs = dfs
                self._ready = True
                logger.info("GraphRAG search engines loaded successfully.")
            except Exception as exc:
                logger.error("Failed to load GraphRAG search engines: %s", exc)
                self._config = None
                self._dfs = {}
                self._ready = False

    def _load_artifacts(self) -> tuple[Any, dict[str, Any]]:
        """
        Load GraphRagConfig from settings.yaml and DataFrames from Parquet.
        graphrag 2.x writes output files directly to output/ (no artifacts/ subdir),
        with simple names: entities.parquet, communities.parquet, etc.

        Must run in a thread (CPU-bound Parquet I/O).
        """
        import sys
        import glob

        # When the server runs with a system Python (not the project venv), graphrag
        # won't be on sys.path because all imports here are deferred. Self-heal by
        # adding the project venv's site-packages directory.
        try:
            import graphrag  # noqa: F401
        except ImportError:
            venv_root = Path(__file__).parent.parent.parent / ".venv" / "lib"
            for sp in sorted(glob.glob(str(venv_root / "python*" / "site-packages"))):
                if sp not in sys.path:
                    sys.path.insert(0, sp)

        import pandas as pd
        from graphrag.config.load_config import load_config

        from app.config import settings

        # graphrag resolves ${GEMINI_API_KEY} from os.environ at load_config time.
        # pydantic-settings does NOT write to os.environ, so inject it here.
        os.environ.setdefault("GEMINI_API_KEY", settings.GEMINI_API_KEY)

        config = load_config(root_dir=self._root)

        # load_config resolves base_dir to an absolute path already.
        try:
            output_dir = Path(config.output.base_dir)
        except AttributeError:
            output_dir = self._root / "output"

        required = [
            "entities",
            "communities",
            "community_reports",
            "text_units",
            "relationships",
        ]
        for name in required:
            path = output_dir / f"{name}.parquet"
            if not path.exists():
                raise FileNotFoundError(
                    f"Artifact not found: {path}. "
                    "Run the indexing pipeline first."
                )

        dfs = {name: pd.read_parquet(output_dir / f"{name}.parquet") for name in required}

        cov_path = output_dir / "covariates.parquet"
        dfs["covariates"] = pd.read_parquet(cov_path) if cov_path.exists() else None

        return config, dfs

    def _extract_sources(self, context: Any) -> list[dict]:
        """Extract source references from GraphRAG context_data (dict of DataFrames)."""
        sources: list[dict] = []

        if not context:
            return sources

        try:
            # graphrag 2.x returns context as dict[str, pd.DataFrame | list[pd.DataFrame]]
            import pandas as pd

            if isinstance(context, dict):
                # Local search: context has "text_units", "reports", "entities" keys
                for key in ("text_units", "sources"):
                    df = context.get(key)
                    if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                        for _, row in df.head(8).iterrows():
                            sources.append({
                                "type": "text_unit",
                                "id": str(row.get("id", "")),
                                "text": str(row.get("text", ""))[:1500],
                                "document": str(row.get("document_id", "")),
                            })
                        break

                reports_df = context.get("reports")
                if reports_df is not None and isinstance(reports_df, pd.DataFrame) and not reports_df.empty:
                    for _, row in reports_df.head(4).iterrows():
                        # graphrag 2.x uses "content" in the context reports df, not "summary"
                        body = row.get("content", row.get("summary", ""))
                        sources.append({
                            "type": "community_report",
                            "id": str(row.get("id", "")),
                            "title": str(row.get("title", "")),
                            "summary": str(body)[:1500],
                        })
        except Exception as exc:
            logger.debug("Could not extract sources from context: %s", exc)

        return sources
