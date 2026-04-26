import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.reasoning import reason
from app.core.reranking import rerank
from app.core.retrieval import retrieve
from app.db.session import get_db
from app.schemas.query import QueryRequest, QueryResponse, RetrievedChunkResponse


router = APIRouter(prefix="/api", tags=["query"])

CANDIDATE_POOL_SIZE = 50


@router.post("/query", response_model=QueryResponse)
def query_endpoint(payload: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    start = time.perf_counter()

    candidates = retrieve(
        db=db,
        query=payload.question,
        patient_id=payload.patient_id,
        k=CANDIDATE_POOL_SIZE,
    )

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail="No clinical data found. Has any patient data been ingested?",
        )

    top_chunks = rerank(
        query=payload.question,
        candidates=candidates,
        top_k=payload.k,
    )

    result = reason(question=payload.question, chunks=top_chunks)

    latency_ms = int((time.perf_counter() - start) * 1000)

    return QueryResponse(
        question=payload.question,
        answer=result.answer,
        chunks=[
            RetrievedChunkResponse(
                chunk_id=c.chunk_id,
                visit_id=c.visit_id,
                visit_date=c.visit_date,
                chunk_index=c.chunk_index,
                chunk_text=c.chunk_text,
                similarity=c.similarity,
            )
            for c in result.chunks_used
        ],
        model=result.model,
        latency_ms=latency_ms,
    )
