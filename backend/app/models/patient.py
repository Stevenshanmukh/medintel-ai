import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class Patient(Base):
    __tablename__ = "patients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    dob = Column(Date, nullable=True)
    sex = Column(String(16), nullable=True)
    mrn = Column(String(64), nullable=True, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    visits = relationship("Visit", back_populates="patient", cascade="all, delete-orphan")
