from __future__ import annotations

from pydantic import BaseModel

DOC_TYPE_LABELS: dict[str, str] = {
    "handbooks": "Sổ tay nhân viên",
    "hr_policies": "Chính sách nhân sự",
    "conduct": "Quy tắc ứng xử",
    "benefits": "Phúc lợi",
    "procedures": "Quy trình",
}


class PolicySource(BaseModel):
    source_file: str
    doc_type: str
    doc_type_label: str = ""
    page_number: int
    excerpt: str
    relevance_score: float
    entities: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.doc_type_label:
            self.doc_type_label = DOC_TYPE_LABELS.get(self.doc_type, self.doc_type)


class IndexingResult(BaseModel):
    chunks_count: int
    nodes_count: int
    edges_count: int
    communities_count: int
    summaries_count: int


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    description: str = ""


class GraphEdge(BaseModel):
    source: str
    relation: str
    target: str


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
