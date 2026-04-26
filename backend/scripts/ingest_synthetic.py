"""
Seed script: load synthetic patient and visits into the database.

Run from inside the backend container:
    docker exec -it medintel_backend python -m scripts.ingest_synthetic
"""
import json
from datetime import datetime
from pathlib import Path

from app.core.ingestion import ingest_visit
from app.db.session import SessionLocal
from app.models import Patient


DATA_FILE = Path("/app/data/synthetic/sarah_chen_visits.json")


def main() -> None:
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Synthetic data not found at {DATA_FILE}. "
            "Make sure data/ is mounted into the container."
        )

    with DATA_FILE.open() as f:
        data = json.load(f)

    db = SessionLocal()
    try:
        existing = db.query(Patient).filter(Patient.mrn == data["patient"]["mrn"]).first()
        if existing:
            print(f"Patient {existing.mrn} already exists (id={existing.id}). Skipping.")
            return

        patient_data = data["patient"]
        patient = Patient(
            name=patient_data["name"],
            dob=datetime.fromisoformat(patient_data["dob"]).date(),
            sex=patient_data["sex"],
            mrn=patient_data["mrn"],
        )
        db.add(patient)
        db.flush()
        print(f"Created patient {patient.name} (id={patient.id})")

        for i, visit_data in enumerate(data["visits"], start=1):
            print(f"Ingesting visit {i}/{len(data['visits'])}: {visit_data['visit_date']}...")
            visit = ingest_visit(
                db=db,
                patient_id=patient.id,
                visit_date=datetime.fromisoformat(visit_data["visit_date"]),
                transcript=visit_data["transcript"],
                chief_complaint=visit_data.get("chief_complaint"),
            )
            print(f"  -> visit {visit.id}: {len(visit.chunks)} chunks embedded")

        print(f"\nDone. Loaded {len(data['visits'])} visits for {patient.name}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
