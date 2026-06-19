from __future__ import annotations

from pydantic import BaseModel, Field
from uuid import uuid4

ENTITY_TYPES = ["CHINH_SACH", "QUY_TAC", "PHONG_BAN", "VAI_TRO", "QUY_TRINH", "QUYEN_LOI", "NGOAI_LE"]
RELATION_TYPES = ["AP_DUNG_CHO", "MIEN_TRU", "GHI_DE", "THAM_CHIEU", "YEU_CAU", "CUNG_CAP", "THUC_THI_BOI"]


class ChunkWithMeta(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    source_file: str
    doc_type: str
    page_number: int
    chunk_index: int


class NodeData(BaseModel):
    name: str
    type: str
    description: str
    source_chunk_ids: list[str] = Field(default_factory=list)
    community_id: int = -1


class EdgeData(BaseModel):
    source: str
    target: str
    relation: str
    source_chunk_id: str = ""
