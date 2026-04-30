"""
Verify risk detection against Sarah Chen's actual data.

Loads visits via build_patient_visits_response (same shape the API will use),
extracts the dict input the detectors expect, runs each detector independently,
and prints raw findings for each.
"""
from app.api.patients import build_patient_visits_response
from app.core.risk_detection import (
    detect_all,
    detect_drug_interactions,
    detect_new_medications,
    detect_symptom_escalation,
)
from app.db.session import SessionLocal


PATIENT_ID = "0a4ed618-2a37-4136-a2ba-c6411e4a3b81"


def visits_to_detector_input(response) -> list[dict]:
    """Reshape Pydantic response into list[dict] the detectors expect."""
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


def run_detector(label: str, findings: list) -> None:
    print("=" * 80)
    print(f"DETECTOR: {label}")
    print("-" * 80)
    if not findings:
        print("(no findings)")
    for f in findings:
        print(f"\n  [{f.severity.upper()}] {f.title}")
        print(f"  Summary: {f.summary}")
        print(f"  Evidence: {f.evidence}")
    print()


if __name__ == "__main__":
    db = SessionLocal()
    try:
        response = build_patient_visits_response(db, PATIENT_ID)
        visits_input = visits_to_detector_input(response)

        print(f"Loaded {len(visits_input)} visits for {response.patient.name}")
        print()

        run_detector(
            "symptom_escalation",
            detect_symptom_escalation(visits_input),
        )
        run_detector(
            "new_medication",
            detect_new_medications(visits_input),
        )
        run_detector(
            "drug_interaction",
            detect_drug_interactions(visits_input),
        )

        print("=" * 80)
        print("AGGREGATE (detect_all, sorted by severity)")
        print("-" * 80)
        all_findings = detect_all(visits_input)
        print(f"Total findings: {len(all_findings)}")
        for f in all_findings:
            print(f"  [{f.severity.upper()}] {f.detector}: {f.title}")
    finally:
        db.close()
