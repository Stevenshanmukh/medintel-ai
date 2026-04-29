from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    patient_id: UUID | None = None
    k: int = Field(default=5, ge=1, le=20)
    match_mode: str = Field(default="loose", pattern="^(loose|strict)$")


class RetrievedChunkResponse(BaseModel):
    chunk_id: str
    visit_id: str
    visit_date: str
    chunk_index: int
    chunk_text: str
    similarity: float


class StructuredEvidenceRow(BaseModel):
    # Fields from existing structured paths (current_medications, first_occurrence,
    # all_mentions). All optional because different paths populate different fields.
    visit_date: str | None = None
    entity_text: str | None = None
    normalized_text: str | None = None
    entity_type: str | None = None
    negated: bool | None = None
    last_visit: str | None = None
    visit_id: str | None = None

    # Fields from compare_visits diffs.
    category: str | None = None         # "medication" | "symptom"
    diff_status: str | None = None      # "added" | "removed" | "new" | "resolved"
    name: str | None = None
    visit_a: str | None = None
    visit_b: str | None = None

    # Fields from trend_over_time series.
    chief_complaint: str | None = None
    present: bool | None = None
    status: str | None = None           # "affirmed" | "denied" | "absent"
    severity: str | None = None
    matched_entities: list[str] | None = None


class QueryResponse(BaseModel):
    question: str
    answer: str
    intent: str
    path: Literal["rag", "structured", "refused"]
    chunks: list[RetrievedChunkResponse] = Field(default_factory=list)
    structured_evidence: list[StructuredEvidenceRow] = Field(default_factory=list)
    model: str
    latency_ms: int
