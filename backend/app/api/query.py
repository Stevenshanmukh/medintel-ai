import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.query_classifier import classify_query
from app.core.reasoning import reason
from app.core.reranking import rerank
from app.core.retrieval import retrieve
from app.core.structured_query import (
    get_all_mentions,
    get_current_medications,
    get_first_occurrence,
    get_unsafe_response,
)
from app.db.session import get_db
from app.schemas.query import (
    QueryRequest,
    QueryResponse,
    RetrievedChunkResponse,
    StructuredEvidenceRow,
)


router = APIRouter(prefix="/api", tags=["query"])

CANDIDATE_POOL_SIZE = 50


def _structured_to_evidence_rows(rows: list[dict]) -> list[StructuredEvidenceRow]:
    out: list[StructuredEvidenceRow] = []
    for r in rows:
        out.append(
            StructuredEvidenceRow(
                visit_date=str(r["visit_date"]) if r.get("visit_date") else None,
                entity_text=r.get("entity_text"),
                normalized_text=r.get("normalized_text"),
                entity_type=r.get("entity_type"),
                negated=r.get("negated"),
                last_visit=str(r["last_visit"]) if r.get("last_visit") else None,
                visit_id=str(r["visit_id"]) if r.get("visit_id") else None,
            )
        )
    return out


@router.post("/query", response_model=QueryResponse)
def query_endpoint(payload: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    start = time.perf_counter()

    classified = classify_query(payload.question)
    intent = classified.intent

    if intent == "current_medications":
        if not payload.patient_id:
            raise HTTPException(400, "patient_id required for medication queries")
        result = get_current_medications(db, payload.patient_id)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return QueryResponse(
            question=payload.question,
            answer=result.answer,
            intent=intent,
            path="structured",
            structured_evidence=_structured_to_evidence_rows(result.evidence_rows),
            model="structured-sql",
            latency_ms=latency_ms,
        )

    if intent == "first_occurrence":
        if not payload.patient_id:
            raise HTTPException(400, "patient_id required for first-occurrence queries")
        if not classified.subject:
            return QueryResponse(
                question=payload.question,
                answer=(
                    "I couldn't identify which symptom or condition you're asking about. "
                    "Try rephrasing — for example, 'When did chest pain first appear?'"
                ),
                intent=intent,
                path="refused",
                model="structured-sql",
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        result = get_first_occurrence(db, payload.patient_id, classified.subject)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return QueryResponse(
            question=payload.question,
            answer=result.answer,
            intent=intent,
            path="structured",
            structured_evidence=_structured_to_evidence_rows(result.evidence_rows),
            model="structured-sql",
            latency_ms=latency_ms,
        )

    if intent == "all_mentions":
        if not payload.patient_id:
            raise HTTPException(400, "patient_id required for all-mentions queries")
        if not classified.subject:
            return QueryResponse(
                question=payload.question,
                answer="I couldn't identify which symptom or medication you're asking about.",
                intent=intent,
                path="refused",
                model="structured-sql",
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        result = get_all_mentions(db, payload.patient_id, classified.subject)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return QueryResponse(
            question=payload.question,
            answer=result.answer,
            intent=intent,
            path="structured",
            structured_evidence=_structured_to_evidence_rows(result.evidence_rows),
            model="structured-sql",
            latency_ms=latency_ms,
        )

    if intent == "unanswerable_or_unsafe":
        result = get_unsafe_response()
        latency_ms = int((time.perf_counter() - start) * 1000)
        return QueryResponse(
            question=payload.question,
            answer=result.answer,
            intent=intent,
            path="refused",
            model="safety-policy",
            latency_ms=latency_ms,
        )

    # Default: narrative_synthesis -> RAG path
    candidates = retrieve(
        db=db,
        query=payload.question,
        patient_id=payload.patient_id,
        k=CANDIDATE_POOL_SIZE,
    )
    if not candidates:
        raise HTTPException(404, "No clinical data found.")

    top_chunks = rerank(query=payload.question, candidates=candidates, top_k=payload.k)
    rag_result = reason(question=payload.question, chunks=top_chunks)
    latency_ms = int((time.perf_counter() - start) * 1000)

    return QueryResponse(
        question=payload.question,
        answer=rag_result.answer,
        intent=intent,
        path="rag",
        chunks=[
            RetrievedChunkResponse(
                chunk_id=c.chunk_id,
                visit_id=c.visit_id,
                visit_date=c.visit_date,
                chunk_index=c.chunk_index,
                chunk_text=c.chunk_text,
                similarity=c.similarity,
            )
            for c in rag_result.chunks_used
        ],
        model=rag_result.model,
        latency_ms=latency_ms,
    )
