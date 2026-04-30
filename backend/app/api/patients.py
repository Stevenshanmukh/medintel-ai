from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from app.core.risk_detection import detect_all
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


class RiskFinding(BaseModel):
    detector: str
    severity: str
    title: str
    summary: str
    evidence: dict[str, Any]


class RiskAlertsResponse(BaseModel):
    patient: PatientHeader
    findings: list[RiskFinding]
    severity_counts: dict[str, int]
    total_visits: int


def _visits_to_detector_input(
    response: "PatientVisitsResponse",
) -> list[dict[str, Any]]:
    """
    Reshape a PatientVisitsResponse into the list-of-dicts shape the
    risk detectors expect. Detectors live in core/ and don't depend on
    Pydantic models — this keeps that boundary clean.
    """
    return [
        {
            "visit_id": v.visit_id,
            "visit_date": v.visit_date,
            "medications_affirmed": v.entities.medications_affirmed,
            "symptoms_affirmed": v.entities.symptoms_affirmed,
            "symptoms_denied": v.entities.symptoms_denied,
        }
        for v in response.visits
    ]


def build_patient_visits_response(
    db: Session,
    patient_id: str,
) -> PatientVisitsResponse:
    """
    Load a patient and all their visits with entities pre-grouped.

    Reusable across endpoints — the visits endpoint and the risk_alerts
    endpoint both need this shape. Raises HTTPException(404) if the patient
    doesn't exist.

    Eager-loads visits and their entities to avoid N+1 queries. Medications
    are filtered against COMMON_MEDICATIONS to drop scispaCy false positives,
    matching the rule used in the structured_query handlers.
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
    return build_patient_visits_response(db, patient_id)


@router.get(
    "/patients/{patient_id}/risk_alerts",
    response_model=RiskAlertsResponse,
)
def get_patient_risk_alerts(
    patient_id: str,
    db: Session = Depends(get_db),
) -> RiskAlertsResponse:
    """
    Run all risk detectors over a patient's structured visit data and
    return findings sorted by severity (high first).

    Detectors are pure functions; this endpoint is the data-loading and
    HTTP shell around them. Computation is deterministic and fast — no
    LLM calls, no external services.
    """
    visits_response = build_patient_visits_response(db, patient_id)
    detector_input = _visits_to_detector_input(visits_response)

    findings = detect_all(detector_input)
    finding_models = [RiskFinding(**f.to_dict()) for f in findings]

    severity_counts = {"high": 0, "moderate": 0, "low": 0}
    for f in findings:
        if f.severity in severity_counts:
            severity_counts[f.severity] += 1

    return RiskAlertsResponse(
        patient=visits_response.patient,
        findings=finding_models,
        severity_counts=severity_counts,
        total_visits=len(visits_response.visits),
    )
