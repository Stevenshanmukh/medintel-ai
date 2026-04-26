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


class QueryResponse(BaseModel):
    question: str
    answer: str
    chunks: list[RetrievedChunkResponse]
    model: str
    latency_ms: int
