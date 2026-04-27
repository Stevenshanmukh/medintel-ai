"""
Verify compare_visits handler against Sarah Chen's 8 visits.

Tests four flows: explicit two-anchor (full diff), explicit two-anchor
with subject filter, implicit compare-to-previous, and edge cases.
"""
import sys
import os
from uuid import UUID

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.structured_query import compare_visits
from app.db.session import SessionLocal


PATIENT_ID = UUID("0a4ed618-2a37-4136-a2ba-c6411e4a3b81")


def run_case(
    label: str,
    anchor_a: str | None,
    anchor_b: str | None,
    subject: str | None = None,
):
    print("=" * 80)
    print(f"CASE: {label}")
    print(f"  anchor_a={anchor_a!r}  anchor_b={anchor_b!r}  subject={subject!r}")
    print("-" * 80)
    db = SessionLocal()
    try:
        result = compare_visits(db, PATIENT_ID, anchor_a, anchor_b, subject)
        print(result.answer)
        print()
        print(f"Evidence rows: {len(result.evidence_rows)}")
        for row in result.evidence_rows:
            print(f"  {row}")
    finally:
        db.close()
    print()


if __name__ == "__main__":
    # 1. Full diff: first visit vs last visit (should show big delta)
    run_case("first visit vs last visit (no subject)", "first visit", "last visit")

    # 2. Subject-filtered: same comparison, narrowed to chest
    run_case(
        "first visit vs last visit, subject='chest pain'",
        "first visit", "last visit",
        subject="chest pain",
    )

    # 3. Adjacent visits around the stent procedure
    run_case("visit 6 vs visit 7 (around stent)", "visit 6", "visit 7")

    # 4. Implicit compare-to-previous: the "since April 2025" case
    run_case("April 2025 vs implicit previous", "April 2025", None,
             subject="chest pain")

    # 5. Edge: first visit, no anchor_b, should refuse
    run_case("first visit, no anchor_b (should refuse)", "first visit", None)

    # 6. Edge: unresolvable anchor, should refuse politely
    run_case("garbage anchor_a (should refuse)",
             "before she started lisinopril", None)
