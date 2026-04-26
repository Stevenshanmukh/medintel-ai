import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class Visit(Base):
    __tablename__ = "visits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    visit_date = Column(DateTime, nullable=False)
    chief_complaint = Column(String(500), nullable=True)
    raw_transcript = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="visits")
    chunks = relationship("VisitChunk", back_populates="visit", cascade="all, delete-orphan")
