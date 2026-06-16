"""
LangChain-backed LLM and embeddings factory.

create_chat_model() → BaseChatModel (unified .ainvoke() interface)
create_embeddings() → Embeddings (unified .embed_query() interface)

Supported providers (set via LLM_PROVIDER env var):
  - gemini      : Google Gemini via langchain-google-genai
  - openai      : OpenAI via langchain-openai
  - siliconflow : DeepSeek/Qwen via OpenAI-compatible endpoint
"""
from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from app.config import settings


def create_chat_model(provider: str | None = None) -> BaseChatModel:
    """
    Create a LangChain BaseChatModel for the specified provider.
    Falls back to LLM_PROVIDER env var, then defaults to "gemini".
    """
    resolved = (provider or settings.LLM_PROVIDER).lower()

    match resolved:
        case "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=settings.GEMINI_CHAT_MODEL,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=0.0,
            )
        case "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=settings.OPENAI_CHAT_MODEL,
                api_key=settings.OPENAI_API_KEY,
                temperature=0.0,
            )
        case "siliconflow":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=settings.SILICONFLOW_MODEL,
                api_key=settings.SILICONFLOW_API_KEY,
                base_url="https://api.siliconflow.cn/v1",
                temperature=0.0,
            )
        case _:
            raise ValueError(f"Unknown LLM_PROVIDER: '{resolved}'. Must be gemini | openai | siliconflow")


def create_embeddings(provider: str | None = None) -> Embeddings:
    """
    Create a LangChain Embeddings object for the specified provider.
    Falls back to LLM_PROVIDER env var, then defaults to "gemini".

    Note on embedding dimensions:
      - Gemini text-embedding-004: 768-dim
      - Gemini gemini-embedding-exp-03-07: 3072-dim (upgrade for production)
      - OpenAI text-embedding-3-small: 1536-dim
      - BAAI/bge-large-zh-v1.5 (Siliconflow): 1024-dim
    """
    resolved = (provider or settings.LLM_PROVIDER).lower()

    match resolved:
        case "gemini":
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            return GoogleGenerativeAIEmbeddings(
                model=f"models/{settings.GEMINI_EMBED_MODEL}",
                google_api_key=settings.GEMINI_API_KEY,
            )
        case "openai":
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(
                model=settings.OPENAI_EMBED_MODEL,
                api_key=settings.OPENAI_API_KEY,
            )
        case "siliconflow":
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(
                model=settings.SILICONFLOW_EMBED_MODEL,
                api_key=settings.SILICONFLOW_API_KEY,
                base_url="https://api.siliconflow.cn/v1",
            )
        case _:
            raise ValueError(f"Unknown LLM_PROVIDER: '{resolved}'. Must be gemini | openai | siliconflow")
