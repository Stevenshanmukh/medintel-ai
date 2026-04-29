from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from app.core.structured_query import _is_real_medication
from app.db.session import get_db
from app.models import Patient, Visit


router = APIRouter(prefix="/api", tags=["patients"])


class PatientResponse(BaseModel):
    id: str
    name: str
    mrn: str | None
    visit_count: int


class VisitEntities(BaseModel):
    medications_affirmed: list[str]
    symptoms_affirmed: list[str]
    symptoms_denied: list[str]


class VisitTimelineEntry(BaseModel):
    visit_id: str
    visit_number: int
    visit_date: str
    chief_complaint: str | None
    raw_transcript: str
    entities: VisitEntities


class PatientHeader(BaseModel):
    id: str
    name: str
    mrn: str | None


class PatientVisitsResponse(BaseModel):
    patient: PatientHeader
    visits: list[VisitTimelineEntry]


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


@router.get(
    "/patients/{patient_id}/visits",
    response_model=PatientVisitsResponse,
)
def get_patient_visits(
    patient_id: str,
    db: Session = Depends(get_db),
) -> PatientVisitsResponse:
    """
    Return all visits for a patient with entities pre-grouped per visit.

    Used by the timeline page. Eager-loads visits and entities to avoid
    N+1 queries. Medications are filtered against COMMON_MEDICATIONS to
    drop scispaCy CHEMICAL false positives, matching the rule used in
    structured_query handlers.
    """
    patient = (
        db.query(Patient)
        .options(selectinload(Patient.visits).selectinload(Visit.entities))
        .filter(Patient.id == patient_id)
        .first()
    )
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    sorted_visits = sorted(patient.visits, key=lambda v: v.visit_date)

    timeline = []
    for idx, visit in enumerate(sorted_visits, start=1):
        meds_affirmed: set[str] = set()
        symptoms_affirmed: set[str] = set()
        symptoms_denied: set[str] = set()

        for ent in visit.entities:
            if ent.entity_type == "medication" and not ent.negated:
                if _is_real_medication(ent.normalized_text):
                    meds_affirmed.add(ent.normalized_text)
            elif ent.entity_type == "symptom":
                if ent.negated:
                    symptoms_denied.add(ent.normalized_text)
                else:
                    symptoms_affirmed.add(ent.normalized_text)

        timeline.append(
            VisitTimelineEntry(
                visit_id=str(visit.id),
                visit_number=idx,
                visit_date=visit.visit_date.date().isoformat(),
                chief_complaint=visit.chief_complaint,
                raw_transcript=visit.raw_transcript,
                entities=VisitEntities(
                    medications_affirmed=sorted(meds_affirmed),
                    symptoms_affirmed=sorted(symptoms_affirmed),
                    symptoms_denied=sorted(symptoms_denied),
                ),
            )
        )

    return PatientVisitsResponse(
        patient=PatientHeader(
            id=str(patient.id),
            name=patient.name,
            mrn=patient.mrn,
        ),
        visits=timeline,
    )
