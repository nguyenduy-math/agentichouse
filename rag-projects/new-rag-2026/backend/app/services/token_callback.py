"""
LangChain callback handler that attributes token usage to a specific session.

One instance is created per chat request. It maps run_id → call_type in
on_llm_start (reading metadata["call_type"] injected by _step_config), then
persists token rows to SQLite via HistoryStore.log_tokens() in on_llm_end.

All SQLite writes are asyncio.create_task() — non-blocking.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

if TYPE_CHECKING:
    from app.services.history_store import HistoryStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pricing table — USD per 1,000 tokens: (prompt_cost, completion_cost)
# Update whenever a new provider/model is added to llm_service.py
# ---------------------------------------------------------------------------
COST_PER_1K: dict[tuple[str, str], tuple[float, float]] = {
    ("openai",      "gpt-4o"):                              (0.0025,  0.0100),
    ("openai",      "gpt-4o-mini"):                         (0.00015, 0.00060),
    ("gemini",      "gemini-2.0-flash"):                    (0.00010, 0.00040),
    ("gemini",      "gemini-2.5-flash"):                    (0.00015, 0.00060),
    ("gemini",      "gemini-2.5-pro"):                      (0.00125, 0.01000),
    ("siliconflow", "deepseek-ai/DeepSeek-V3"):             (0.00014, 0.00028),
    ("siliconflow", "Qwen/Qwen2.5-72B-Instruct"):           (0.00040, 0.00040),
    ("siliconflow", "BAAI/bge-large-zh-v1.5"):              (0.00000, 0.00000),
}


def _estimate_cost(
    provider: str, model: str, prompt_tokens: int, completion_tokens: int
) -> float:
    """Return estimated cost in USD. Returns 0.0 for unknown models."""
    key = (provider, model)
    if key not in COST_PER_1K:
        return 0.0
    prompt_rate, completion_rate = COST_PER_1K[key]
    return (prompt_tokens / 1000 * prompt_rate) + (completion_tokens / 1000 * completion_rate)


def _extract_tokens(response: LLMResult, provider: str) -> tuple[int, int]:
    """
    Extract (prompt_tokens, completion_tokens) from LLMResult.

    Provider-specific formats:
    - Gemini (langchain-google-genai):
        response.llm_output["usage_metadata"] = {
            "prompt_token_count": int,
            "candidates_token_count": int,
            "total_token_count": int,
        }
    - OpenAI / Siliconflow (OpenAI-compatible):
        response.llm_output["token_usage"] = {
            "prompt_tokens": int,
            "completion_tokens": int,
            "total_tokens": int,
        }
    """
    if not response.llm_output:
        return 0, 0

    if provider == "gemini":
        meta = response.llm_output.get("usage_metadata", {})
        return (
            meta.get("prompt_token_count", 0),
            meta.get("candidates_token_count", 0),
        )

    # openai + siliconflow (OpenAI-compatible)
    usage = response.llm_output.get("token_usage", {})
    return (
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
    )


class SessionTokenCallback(BaseCallbackHandler):
    """
    Single callback instance per chat request.

    Routes each LLM call to the correct call_type by reading
    metadata["call_type"] in on_llm_start (injected by _step_config in
    orchestrator.py / base_agent.py).

    Thread safety: _active_run_types is a plain dict accessed only from the
    asyncio event loop (LangChain callbacks fire in the same loop).
    """

    raise_error = False  # never propagate callback exceptions to the LLM response path

    def __init__(
        self,
        session_id: str,
        token_store: "HistoryStore",
        provider: str,
        model: str,
        turn_id: str | None = None,
    ) -> None:
        super().__init__()
        self.session_id = session_id
        self._store = token_store
        self.provider = provider
        self.model = model
        self.turn_id = turn_id
        # Maps str(run_id) → call_type; populated in on_llm_start
        self._active_run_types: dict[str, str] = {}

    def set_turn_id(self, turn_id: str) -> None:
        """
        Back-fill the turn_id after history_store.save_turn() resolves its UUID.
        Called from chat.py after the orchestrator returns.
        """
        self.turn_id = turn_id

    # ------------------------------------------------------------------
    # LangChain hooks
    # ------------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Map run_id → call_type using metadata["call_type"] from _step_config."""
        call_type = (metadata or {}).get("call_type", "unknown")
        self._active_run_types[str(run_id)] = call_type

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        call_type = self._active_run_types.pop(str(run_id), "unknown")
        prompt_tokens, completion_tokens = _extract_tokens(response, self.provider)
        total_tokens = prompt_tokens + completion_tokens
        cost = _estimate_cost(self.provider, self.model, prompt_tokens, completion_tokens)

        asyncio.create_task(
            self._store.log_tokens(
                session_id=self.session_id,
                turn_id=self.turn_id,
                call_type=call_type,
                provider=self.provider,
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost,
                error=False,
            )
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        call_type = self._active_run_types.pop(str(run_id), "unknown")
        logger.warning(
            "LLM error captured by SessionTokenCallback session=%s call_type=%s error=%s",
            self.session_id,
            call_type,
            str(error),
        )
        asyncio.create_task(
            self._store.log_tokens(
                session_id=self.session_id,
                turn_id=self.turn_id,
                call_type=call_type,
                provider=self.provider,
                model=self.model,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost_usd=0.0,
                error=True,
            )
        )
