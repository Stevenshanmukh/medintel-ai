from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Patient


router = APIRouter(prefix="/api", tags=["patients"])


class PatientResponse(BaseModel):
    id: str
    name: str
    mrn: str | None
    visit_count: int


@router.get("/patients", response_model=list[PatientResponse])
def list_patients(db: Session = Depends(get_db)) -> list[PatientResponse]:
    patients = db.query(Patient).all()
    return [
        PatientResponse(
            id=str(p.id),
            name=p.name,
            mrn=p.mrn,
            visit_count=len(p.visits),
        )
        for p in patients
    ]
