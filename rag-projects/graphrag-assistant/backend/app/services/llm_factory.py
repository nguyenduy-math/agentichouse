from __future__ import annotations

from app.config import settings


def create_llm_service():
    """Return the LLM service instance based on LLM_PROVIDER in .env."""
    if settings.llm_provider.lower() == "openai":
        from app.services.openai_llm_service import OpenAILLMService
        return OpenAILLMService()
    from app.services.llm_service import LLMService
    return LLMService()
