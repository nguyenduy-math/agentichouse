"""LightRAGService — per-domain LightRAG instance with Gemini LLM/embedding wrappers.

Each domain agent creates its own LightRAGService with a distinct working_dir so
vector + KV stores are isolated per domain. All instances share the same Neo4j
database but use domain-specific entity types to keep graph knowledge focused.

The Gemini wrappers are lifted verbatim from lightrag-assistant's rag_engine.py.
"""

from __future__ import annotations

import json
import logging
import os
import re

import numpy as np
from google import genai
from google.genai import types
from lightrag import LightRAG, QueryParam
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.utils import EmbeddingFunc

from app.config import settings

logger = logging.getLogger(__name__)


class LightRAGService:
    def __init__(self, working_dir: str, entity_types: list[str]) -> None:
        self._working_dir = working_dir
        self._entity_types = entity_types
        self._rag: LightRAG | None = None
        self._gemini_client: genai.Client | None = None

    # ------------------------------------------------------------------
    # Gemini wrappers — signatures match what LightRAG calls them with.
    # Copied verbatim from lightrag-assistant/backend/app/rag_engine.py.
    # ------------------------------------------------------------------

    def _client(self) -> genai.Client:
        if self._gemini_client is None:
            self._gemini_client = genai.Client(api_key=settings.gemini_api_key)
        return self._gemini_client

    async def _llm_func(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict] | None = None,
        keyword_extraction: bool = False,
        **kwargs,
    ) -> str:
        history_messages = history_messages or []
        contents: list[types.Content] = []
        for message in history_messages:
            role = "model" if message.get("role") == "assistant" else "user"
            contents.append(
                types.Content(role=role, parts=[types.Part(text=message.get("content", ""))])
            )
        contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
        config = types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            temperature=kwargs.get("temperature", 0.2),
        )
        response = await self._client().aio.models.generate_content(
            model=settings.gemini_llm_model,
            contents=contents,
            config=config,
        )
        try:
            return response.text or ""
        except Exception as exc:
            logger.warning("Gemini returned no text: %s", exc)
            return ""

    async def _embedding_func(self, texts: list[str]) -> np.ndarray:
        response = await self._client().aio.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=texts,
            config=types.EmbedContentConfig(output_dimensionality=settings.embedding_dim),
        )
        vectors = np.array(
            [embedding.values for embedding in response.embeddings], dtype=np.float32
        )
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        os.makedirs(self._working_dir, exist_ok=True)

        os.environ["NEO4J_URI"] = settings.neo4j_uri
        os.environ["NEO4J_USERNAME"] = settings.neo4j_username
        os.environ["NEO4J_PASSWORD"] = settings.neo4j_password
        os.environ["NEO4J_DATABASE"] = settings.neo4j_database

        rag = LightRAG(
            working_dir=self._working_dir,
            llm_model_func=self._llm_func,
            llm_model_name=settings.gemini_llm_model,
            embedding_func=EmbeddingFunc(
                embedding_dim=settings.embedding_dim,
                max_token_size=settings.embedding_max_token_size,
                func=self._embedding_func,
            ),
            graph_storage="Neo4JStorage",
            addon_params={
                "language": settings.response_language,
                "entity_types": self._entity_types,
            },
        )
        await rag.initialize_storages()
        await initialize_pipeline_status()
        self._rag = rag
        logger.info(
            "LightRAGService initialized — dir: %s, LLM: %s",
            self._working_dir,
            settings.gemini_llm_model,
        )

    async def shutdown(self) -> None:
        if self._rag is not None:
            await self._rag.finalize_storages()
            self._rag = None
            logger.info("LightRAGService finalized: %s", self._working_dir)

    def is_ready(self) -> bool:
        return self._rag is not None

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def insert(self, texts: list[str], file_paths: list[str]) -> None:
        if self._rag is None:
            raise RuntimeError(f"LightRAGService not initialized: {self._working_dir}")
        await self._rag.ainsert(texts, file_paths=file_paths)

    async def query(
        self,
        question: str,
        mode: str = "hybrid",
        history: list[dict] | None = None,
        user_prompt: str | None = None,
    ) -> str:
        if self._rag is None:
            raise RuntimeError(f"LightRAGService not initialized: {self._working_dir}")
        param = QueryParam(
            mode=mode,
            conversation_history=history or [],
            user_prompt=user_prompt or "",
        )
        return str(await self._rag.aquery(question, param=param))

    async def retrieve_entities(self, question: str, mode: str = "hybrid", limit: int = 12) -> list[str]:
        """Return the knowledge-graph entity names backing an answer.

        Uses a retrieval-only query (``only_need_context=True`` — no generation, so
        it's cheaper than answering) and defensively parses whatever shape LightRAG
        returns. Any failure yields an empty list; this never raises.

        Audit ref: B3 (the API advertised ``entities`` but it was always empty).
        """
        if self._rag is None:
            return []
        try:
            param = QueryParam(mode=mode, only_need_context=True)
            context = str(await self._rag.aquery(question, param=param))
            return _parse_entity_names(context)[:limit]
        except Exception as exc:  # noqa: BLE001 - entities are best-effort
            logger.warning("retrieve_entities failed (%s)", exc)
            return []

    async def check_neo4j(self) -> bool:
        from neo4j import AsyncGraphDatabase

        driver = None
        try:
            driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password),
            )
            await driver.verify_connectivity()
            return True
        except Exception as exc:
            logger.warning("Neo4j connectivity check failed: %s", exc)
            return False
        finally:
            if driver is not None:
                await driver.close()


# Keys LightRAG has used for the entity name across versions, in priority order.
_ENTITY_NAME_KEYS = ("entity", "entity_name", "name", "entity_id")


def _parse_entity_names(context: str) -> list[str]:
    """Extract distinct entity names from a LightRAG ``only_need_context`` payload.

    Handles both the JSON shape (``{"entities": [{...}], ...}``) used by recent
    versions and the older ``-----Entities-----`` CSV block, degrading to [] if the
    format is unrecognized. De-dupes while preserving order.
    """
    names: list[str] = []

    # 1) Modern JSON payload.
    try:
        data = json.loads(context)
        entities = data.get("entities") if isinstance(data, dict) else None
        if isinstance(entities, list):
            for ent in entities:
                if isinstance(ent, dict):
                    for key in _ENTITY_NAME_KEYS:
                        if ent.get(key):
                            names.append(str(ent[key]).strip())
                            break
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass

    # 2) Fallback: legacy "-----Entities-----" CSV block.
    if not names and "Entities" in context:
        block = re.split(r"-+\s*Entities\s*-+", context, maxsplit=1)
        if len(block) > 1:
            tail = re.split(r"-+\s*(Relationships|Relations|Sources)\s*-+", block[1])[0]
            for line in tail.splitlines():
                cells = [c.strip().strip('"') for c in line.split(",")]
                # Skip header / id rows; take the first non-numeric, non-keyword cell.
                for cell in cells[1:]:
                    if cell and not cell.isdigit() and cell.lower() not in {"entity", "name", "type"}:
                        names.append(cell)
                        break

    # De-dupe, preserve order, drop empties.
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out
