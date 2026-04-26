from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.chunking import chunk_text
from app.core.embeddings import embed_texts
from app.models import Visit, VisitChunk


def ingest_visit(
    db: Session,
    patient_id: UUID,
    visit_date: datetime,
    transcript: str,
    chief_complaint: str | None = None,
) -> Visit:
    """
    Create a Visit record, chunk the transcript, embed each chunk, and store.

    Returns the created Visit (with chunks attached).
    """
    visit = Visit(
        patient_id=patient_id,
        visit_date=visit_date,
        chief_complaint=chief_complaint,
        raw_transcript=transcript,
    )
    db.add(visit)
    db.flush()

    chunks = chunk_text(transcript, chunk_size=500, overlap=50)
    if not chunks:
        db.commit()
        return visit

    embeddings = embed_texts(chunks)

    for idx, (chunk_str, embedding) in enumerate(zip(chunks, embeddings)):
        visit_chunk = VisitChunk(
            visit_id=visit.id,
            chunk_index=idx,
            chunk_text=chunk_str,
            chunk_type="transcript_segment",
            embedding=embedding,
            chunk_metadata={
                "patient_id": str(patient_id),
                "visit_date": visit_date.isoformat(),
                "visit_id": str(visit.id),
            },
        )
        db.add(visit_chunk)

    db.commit()
    db.refresh(visit)
    return visit
