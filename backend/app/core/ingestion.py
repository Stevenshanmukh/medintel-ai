from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.chunking import chunk_text
from app.core.embeddings import embed_texts
from app.core.entities import extract_entities
from app.models import Visit, VisitChunk, VisitEntity


def ingest_visit(
    db: Session,
    patient_id: UUID,
    visit_date: datetime,
    transcript: str,
    chief_complaint: str | None = None,
) -> Visit:
    """
    Create a Visit record. Process the transcript along three parallel tracks:
      1. Chunk + embed for semantic retrieval (visit_chunks)
      2. Extract clinical entities for structured queries (visit_entities)
      3. Store raw transcript on the visit itself (full text fallback)

    All three are committed atomically.
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
    if chunks:
        embeddings = embed_texts(chunks)
        for idx, (chunk_str, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(
                VisitChunk(
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
            )

    entities = extract_entities(transcript)
    for ent in entities:
        db.add(
            VisitEntity(
                visit_id=visit.id,
                entity_type=ent.entity_type,
                entity_text=ent.entity_text,
                normalized_text=ent.normalized_text,
                negated=ent.negated,
                severity=ent.severity,
                duration=ent.duration,
                char_start=ent.char_start,
                char_end=ent.char_end,
                confidence=ent.confidence,
                extra=ent.extra,
            )
        )

    db.commit()
    db.refresh(visit)
    return visit
