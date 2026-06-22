from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Gemini
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "models/gemini-embedding-exp-03-07"
    embedding_dim: int = 3072

    # Storage
    chroma_persist_dir: str = "./storage/chroma"
    bm25_index_path: str = "./storage/bm25_index.pkl"

    # Retrieval
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_top_n: int = 5
    # Chunks with rerank score below this are considered out-of-scope
    min_rerank_score: float = -1.0

    # Session
    max_history_messages: int = 10
    session_ttl_seconds: int = 3600

    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200


settings = Settings()
