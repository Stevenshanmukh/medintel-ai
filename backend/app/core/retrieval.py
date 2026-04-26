from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.embeddings import embed_text


@dataclass
class RetrievedChunk:
    """A chunk returned from retrieval, with its similarity score and context."""
    chunk_id: str
    visit_id: str
    visit_date: str
    chunk_index: int
    chunk_text: str
    similarity: float


def retrieve(
    db: Session,
    query: str,
    patient_id: UUID | None = None,
    k: int = 5,
) -> list[RetrievedChunk]:
    """
    Retrieve the top-k most semantically similar chunks for a query.

    Uses pgvector's cosine distance operator (<=>). Since we normalize embeddings
    at ingestion time, cosine distance equals 1 - cosine_similarity, so we convert
    back to similarity for human readability.

    If patient_id is provided, results are filtered to that patient only.
    """
    query_embedding = embed_text(query)

    sql = """
        SELECT
            vc.id::text AS chunk_id,
            vc.visit_id::text AS visit_id,
            v.visit_date::text AS visit_date,
            vc.chunk_index,
            vc.chunk_text,
            1 - (vc.embedding <=> CAST(:qvec AS vector)) AS similarity
        FROM visit_chunks vc
        JOIN visits v ON v.id = vc.visit_id
        WHERE (CAST(:patient_id AS uuid) IS NULL OR v.patient_id = CAST(:patient_id AS uuid))
        ORDER BY vc.embedding <=> CAST(:qvec AS vector)
        LIMIT :k
    """

    result = db.execute(
        text(sql),
        {
            "qvec": str(query_embedding),
            "patient_id": str(patient_id) if patient_id else None,
            "k": k,
        },
    )

    return [
        RetrievedChunk(
            chunk_id=row.chunk_id,
            visit_id=row.visit_id,
            visit_date=row.visit_date,
            chunk_index=row.chunk_index,
            chunk_text=row.chunk_text,
            similarity=float(row.similarity),
        )
        for row in result
    ]
