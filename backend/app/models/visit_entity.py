import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Float, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


class VisitEntity(Base):
    __tablename__ = "visit_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visit_id = Column(UUID(as_uuid=True), ForeignKey("visits.id"), nullable=False, index=True)

    entity_type = Column(String(32), nullable=False, index=True)
    entity_text = Column(String(500), nullable=False)
    normalized_text = Column(String(500), nullable=False, index=True)

    negated = Column(Boolean, nullable=False, default=False)
    severity = Column(String(32), nullable=True)
    duration = Column(String(64), nullable=True)

    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)

    confidence = Column(Float, nullable=True)
    extra = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    visit = relationship("Visit", back_populates="entities")
