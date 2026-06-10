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

import os

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel


def create_chat_model(provider: str | None = None) -> BaseChatModel:
    """
    Create a LangChain BaseChatModel for the specified provider.
    Falls back to LLM_PROVIDER env var, then defaults to "gemini".
    """
    resolved = (provider or os.environ.get("LLM_PROVIDER", "gemini")).lower()

    match resolved:
        case "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.0-flash"),
                google_api_key=os.environ.get("GEMINI_API_KEY", ""),
                temperature=0.0,
            )
        case "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o"),
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                temperature=0.0,
            )
        case "siliconflow":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=os.environ.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3"),
                api_key=os.environ.get("SILICONFLOW_API_KEY", ""),
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
    resolved = (provider or os.environ.get("LLM_PROVIDER", "gemini")).lower()

    match resolved:
        case "gemini":
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            return GoogleGenerativeAIEmbeddings(
                model=os.environ.get(
                    "GEMINI_EMBED_MODEL", "models/text-embedding-004"
                ),
                google_api_key=os.environ.get("GEMINI_API_KEY", ""),
            )
        case "openai":
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(
                model=os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
                api_key=os.environ.get("OPENAI_API_KEY", ""),
            )
        case "siliconflow":
            # Siliconflow is OpenAI-compatible — use OpenAIEmbeddings with base_url
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(
                model=os.environ.get(
                    "SILICONFLOW_EMBED_MODEL", "BAAI/bge-large-zh-v1.5"
                ),
                api_key=os.environ.get("SILICONFLOW_API_KEY", ""),
                base_url="https://api.siliconflow.cn/v1",
            )
        case _:
            raise ValueError(f"Unknown LLM_PROVIDER: '{resolved}'. Must be gemini | openai | siliconflow")
