"""
Verify trend_over_time handler against Sarah Chen's 8 visits.

Tests the main use cases: a symptom that progresses (chest pain),
a medication's presence (lisinopril), an absent subject, and the
no-subject refusal.
"""
import sys
import os
from uuid import UUID

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.structured_query import trend_over_time
from app.db.session import SessionLocal


PATIENT_ID = UUID("0a4ed618-2a37-4136-a2ba-c6411e4a3b81")


def run_case(label: str, subject: str | None):
    print("=" * 80)
    print(f"CASE: {label}")
    print(f"  subject={subject!r}")
    print("-" * 80)
    db = SessionLocal()
    try:
        result = trend_over_time(db, PATIENT_ID, subject)
        print(result.answer)
        print()
        print(f"Series rows: {len(result.evidence_rows)}")
        for row in result.evidence_rows:
            print(f"  {row}")
    finally:
        db.close()
    print()


if __name__ == "__main__":
    # 1. Symptom trajectory: chest pain across all 8 visits
    run_case("chest pain trajectory", "chest pain")

    # 2. A different symptom: shortness of breath
    run_case("shortness of breath trajectory", "shortness of breath")

    # 3. Fatigue — should appear in early visits, resolved later
    run_case("fatigue trajectory", "fatigue")

    # 4. Medication presence: lisinopril (should be in all 8)
    run_case("lisinopril presence", "lisinopril")

    # 5. Medication that appears mid-arc: clopidogrel
    run_case("clopidogrel presence", "clopidogrel")

    # 6. Subject that doesn't exist
    run_case("nonexistent subject", "diabetes")

    # 7. No subject — should refuse
    run_case("no subject (should refuse)", None)
