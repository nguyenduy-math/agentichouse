"""LightRAG engine lifecycle + Google Gemini LLM/embedding wrappers.

The Gemini wrappers are written directly against the ``google-genai`` SDK rather
than depending on LightRAG's internal gemini binding — this keeps the exact
function signatures LightRAG expects under our control and insulates us from
changes in LightRAG's optional bindings. The wrappers stay thin: build the
request, call Gemini, return text or vectors.

The single ``LightRAG`` instance is created once at app startup (see
``app/main.py`` lifespan) and shared across all requests.
"""

from __future__ import annotations

import logging
import os

import numpy as np
from google import genai
from google.genai import types
from lightrag import LightRAG
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.utils import EmbeddingFunc

from app.config import settings
from app.domain import INSURANCE_ENTITY_TYPES

logger = logging.getLogger(__name__)

_rag: LightRAG | None = None
_gemini_client: genai.Client | None = None


def _client() -> genai.Client:
    """Lazily build the shared async-capable Gemini client."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


# --------------------------------------------------------------------------
# Gemini wrappers — signatures match what LightRAG calls them with.
# --------------------------------------------------------------------------
async def gemini_llm_func(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict] | None = None,
    keyword_extraction: bool = False,
    **kwargs,
) -> str:
    """LLM completion wrapper for LightRAG (``llm_model_func``)."""
    history_messages = history_messages or []

    contents: list[types.Content] = []
    for message in history_messages:
        # Gemini expects the role "model" for assistant turns.
        role = "model" if message.get("role") == "assistant" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part(text=message.get("content", ""))])
        )
    contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))

    config = types.GenerateContentConfig(
        system_instruction=system_prompt or None,
        temperature=kwargs.get("temperature", 0.2),
    )

    response = await _client().aio.models.generate_content(
        model=settings.gemini_llm_model,
        contents=contents,
        config=config,
    )
    try:
        return response.text or ""
    except Exception as exc:  # noqa: BLE001 - blocked/empty response, keep pipeline alive
        logger.warning("Gemini returned no text: %s", exc)
        return ""


async def gemini_embedding_func(texts: list[str]) -> np.ndarray:
    """Embedding wrapper for LightRAG. Returns shape (len(texts), embedding_dim)."""
    response = await _client().aio.models.embed_content(
        model=settings.gemini_embedding_model,
        contents=texts,
        config=types.EmbedContentConfig(output_dimensionality=settings.embedding_dim),
    )
    vectors = np.array([embedding.values for embedding in response.embeddings], dtype=np.float32)

    # gemini-embedding-001 returns un-normalized vectors for any output dimension
    # other than 3072 — normalize so cosine similarity behaves correctly.
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


# --------------------------------------------------------------------------
# LightRAG lifecycle
# --------------------------------------------------------------------------
async def init_rag() -> LightRAG:
    """Construct the LightRAG instance and run its async initialization.

    Must be called inside a running event loop (FastAPI lifespan). Both
    ``initialize_storages()`` and ``initialize_pipeline_status()`` are required.
    """
    global _rag

    os.makedirs(settings.working_dir, exist_ok=True)

    # LightRAG's Neo4JStorage reads its connection from these env vars — set them
    # explicitly from config so config.py stays the single source of truth.
    os.environ["NEO4J_URI"] = settings.neo4j_uri
    os.environ["NEO4J_USERNAME"] = settings.neo4j_username
    os.environ["NEO4J_PASSWORD"] = settings.neo4j_password
    os.environ["NEO4J_DATABASE"] = settings.neo4j_database

    rag = LightRAG(
        working_dir=settings.working_dir,
        llm_model_func=gemini_llm_func,
        llm_model_name=settings.gemini_llm_model,
        embedding_func=EmbeddingFunc(
            embedding_dim=settings.embedding_dim,
            max_token_size=settings.embedding_max_token_size,
            func=gemini_embedding_func,
        ),
        graph_storage="Neo4JStorage",
        addon_params={
            "language": settings.response_language,
            "entity_types": INSURANCE_ENTITY_TYPES,
        },
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()

    _rag = rag
    logger.info(
        "LightRAG initialized — graph storage: Neo4j (%s), LLM: %s, embeddings: %s @ %dd",
        settings.neo4j_uri,
        settings.gemini_llm_model,
        settings.gemini_embedding_model,
        settings.embedding_dim,
    )
    return rag


async def shutdown_rag() -> None:
    """Finalize LightRAG storages (closes the Neo4j driver, flushes files)."""
    global _rag
    if _rag is not None:
        await _rag.finalize_storages()
        _rag = None
        logger.info("LightRAG storages finalized.")


def get_rag() -> LightRAG:
    """FastAPI dependency — returns the live LightRAG instance or raises."""
    if _rag is None:
        raise RuntimeError("RAG engine is not initialized yet.")
    return _rag


def is_initialized() -> bool:
    return _rag is not None


async def check_neo4j() -> bool:
    """Lightweight Neo4j connectivity probe for the /health endpoint."""
    from neo4j import AsyncGraphDatabase

    driver = None
    try:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
        await driver.verify_connectivity()
        return True
    except Exception as exc:  # noqa: BLE001 - report as "not connected" in /health
        logger.warning("Neo4j connectivity check failed: %s", exc)
        return False
    finally:
        if driver is not None:
            await driver.close()
