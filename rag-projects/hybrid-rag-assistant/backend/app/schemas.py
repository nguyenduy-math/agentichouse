from pydantic import BaseModel, Field


class SessionCreateResponse(BaseModel):
    session_id: str


class HistoryMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChunkSource(BaseModel):
    chunk_id: str
    source_file: str
    page_number: int
    chunk_index: int
    excerpt: str
    rerank_score: float
    domain: str = "general"


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    rewritten_query: str
    domains_used: list[str] = []
    is_out_of_scope: bool = False
    sources: list[ChunkSource]


class IndexStatusResponse(BaseModel):
    status: str  # "idle" | "running" | "done" | "error"
    message: str = ""
    chunks_indexed: int = 0


class StatsResponse(BaseModel):
    total_chunks: int
    bm25_corpus_size: int
