from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    patient_id: UUID | None = None
    k: int = Field(default=5, ge=1, le=20)


class RetrievedChunkResponse(BaseModel):
    chunk_id: str
    visit_id: str
    visit_date: str
    chunk_index: int
    chunk_text: str
    similarity: float


class StructuredEvidenceRow(BaseModel):
    visit_date: str | None = None
    entity_text: str | None = None
    normalized_text: str | None = None
    entity_type: str | None = None
    negated: bool | None = None
    last_visit: str | None = None
    visit_id: str | None = None


class QueryResponse(BaseModel):
    question: str
    answer: str
    intent: str
    path: Literal["rag", "structured", "refused"]
    chunks: list[RetrievedChunkResponse] = Field(default_factory=list)
    structured_evidence: list[StructuredEvidenceRow] = Field(default_factory=list)
    model: str
    latency_ms: int
