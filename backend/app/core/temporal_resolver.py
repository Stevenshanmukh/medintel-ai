"""
Resolves natural-language temporal anchors to specific visit_ids.

Used by compare_visits and trend_over_time handlers in structured_query.py.
Pure logic over the visits table — no LLM calls, deterministic, unit-testable.

Resolution priority (first match wins):
  1. Explicit ISO date         "2025-04-05"
  2. Month + year              "April 2025", "April of 2025"
  3. Visit number              "visit 3", "the third visit", "visit #3"
  4. Ordinal/relative phrases  "first", "last", "most recent", "previous", "initial"
  5. Unresolved                fall through, caller decides what to do
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


ResolutionMethod = Literal[
    "explicit_date",
    "month_year",
    "visit_number",
    "ordinal_first",
    "ordinal_last",
    "ordinal_previous",
    "ordinal_nth",
    "unresolved",
]


@dataclass
class ResolvedAnchor:
    visit_id: UUID
    visit_date: date
    visit_number: int  # 1-indexed, sorted by visit_date ASC
    chief_complaint: str | None
    resolution_method: ResolutionMethod
    matched_phrase: str  # what we actually matched on, for UI explainability


# Phrase tables. Order in ORDINAL_NTH matters (longer matches first).
ORDINAL_FIRST = {"first", "initial", "earliest", "1st"}
ORDINAL_LAST = {"last", "latest", "most recent", "recent", "current"}
ORDINAL_PREVIOUS = {"previous", "prior", "before that", "the one before"}
ORDINAL_NTH = {
    "second": 2, "2nd": 2,
    "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4,
    "fifth": 5, "5th": 5,
    "sixth": 6, "6th": 6,
    "seventh": 7, "7th": 7,
    "eighth": 8, "8th": 8,
}

MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# Patterns
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MONTH_YEAR_RE = re.compile(
    r"\b(" + "|".join(MONTH_NAMES.keys()) + r")\s+(?:of\s+)?(\d{4})\b",
    re.IGNORECASE,
)
VISIT_NUMBER_RE = re.compile(r"\bvisit\s+#?\s*(\d+)\b", re.IGNORECASE)


def _load_visits(db: Session, patient_id: UUID) -> list[dict]:
    """Return all visits for a patient, sorted by date ascending, with row numbers."""
    sql = """
        SELECT
            id,
            visit_date::date AS visit_date,
            chief_complaint,
            ROW_NUMBER() OVER (ORDER BY visit_date) AS visit_number
        FROM visits
        WHERE patient_id = CAST(:patient_id AS uuid)
        ORDER BY visit_date
    """
    rows = db.execute(text(sql), {"patient_id": str(patient_id)}).mappings().all()
    return [dict(r) for r in rows]


def _to_anchor(row: dict, method: ResolutionMethod, matched_phrase: str) -> ResolvedAnchor:
    return ResolvedAnchor(
        visit_id=row["id"],
        visit_date=row["visit_date"],
        visit_number=row["visit_number"],
        chief_complaint=row["chief_complaint"],
        resolution_method=method,
        matched_phrase=matched_phrase,
    )


def resolve_anchor(
    db: Session,
    patient_id: UUID,
    anchor_phrase: str | None,
) -> ResolvedAnchor | None:
    """
    Resolve a natural-language anchor phrase to a specific visit.

    Returns None if the phrase is empty, no visits exist, or no rule matches.
    Caller is responsible for deciding fallback behavior.

    WARNING: This should be called on extracted temporal segments, not the full question,
    to avoid false positives on words like 'initial' or 'last' appearing elsewhere.
    """
    if not anchor_phrase:
        return None

    visits = _load_visits(db, patient_id)
    if not visits:
        return None

    phrase = anchor_phrase.strip().lower()

    # Rule 1: explicit ISO date
    iso_match = ISO_DATE_RE.search(phrase)
    if iso_match:
        try:
            target = date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
            for v in visits:
                if v["visit_date"] == target:
                    return _to_anchor(v, "explicit_date", iso_match.group(0))
        except ValueError:
            pass # Invalid date string

    # Rule 2: month + year (match within the calendar month)
    my_match = MONTH_YEAR_RE.search(phrase)
    if my_match:
        month = MONTH_NAMES[my_match.group(1).lower()]
        year = int(my_match.group(2))
        for v in visits:
            if v["visit_date"].year == year and v["visit_date"].month == month:
                return _to_anchor(v, "month_year", my_match.group(0))

    # Rule 3: visit number ("visit 3", "visit #3")
    vn_match = VISIT_NUMBER_RE.search(phrase)
    if vn_match:
        n = int(vn_match.group(1))
        if 1 <= n <= len(visits):
            return _to_anchor(visits[n - 1], "visit_number", vn_match.group(0))

    # Rule 4a: ordinal "first" / "initial" / etc.
    if any(re.search(rf"\b{word}\b", phrase) for word in ORDINAL_FIRST):
        return _to_anchor(visits[0], "ordinal_first", phrase)

    # Rule 4b: ordinal "last" / "most recent" / "current" / etc.
    if any(re.search(rf"\b{word}\b", phrase) for word in ORDINAL_LAST):
        return _to_anchor(visits[-1], "ordinal_last", phrase)

    # Rule 4c: "previous" / "prior" — second-to-last
    if any(re.search(rf"\b{word}\b", phrase) for word in ORDINAL_PREVIOUS):
        if len(visits) >= 2:
            return _to_anchor(visits[-2], "ordinal_previous", phrase)
        return None  # only one visit, "previous" is undefined

    # Rule 4d: "second", "third", etc. — only if not already matched as visit number
    for word, n in ORDINAL_NTH.items():
        if re.search(rf"\b{word}\b", phrase):
            if 1 <= n <= len(visits):
                return _to_anchor(visits[n - 1], "ordinal_nth", word)

    # Rule 5: unresolved
    return None


def get_previous_visit(db: Session, patient_id: UUID, visit_id: UUID) -> ResolvedAnchor | None:
    """
    Return the visit immediately before the given visit_id, by date.
    Used for implicit compare-to-previous when only one anchor is provided.
    Returns None if visit_id is the first visit or not found.
    """
    visits = _load_visits(db, patient_id)
    for i, v in enumerate(visits):
        if v["id"] == visit_id and i > 0:
            return _to_anchor(visits[i - 1], "ordinal_previous", "implicit previous")
    return None
