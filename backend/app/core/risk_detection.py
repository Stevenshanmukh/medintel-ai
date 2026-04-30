"""
Risk detection: rule-based clinical pattern detectors over structured visit data.

Each detector is a pure function that takes a patient's visits + entities and
returns a list of Finding objects. No database session, no LLM calls — fully
deterministic and unit-testable. The API layer assembles the input data and
calls these functions.

Three detectors implemented for v1:
  1. symptom_escalation: a symptom affirmed in 3+ recent consecutive visits
  2. new_medication: a medication present at the latest visit but absent
     from all earlier visits
  3. drug_interaction: pairs of currently-active medications matching curated
     known-interaction list

Future detectors documented but not implemented:
  - symptom_relapse: affirmed → denied → affirmed pattern
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Literal


Severity = Literal["low", "moderate", "high"]


@dataclass
class Finding:
    """A single risk-detection finding for a patient."""
    detector: str
    severity: Severity
    title: str
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- Input data shape --------------------------------------------------------
#
# The detectors expect a list of "visit summaries" — one dict per visit, sorted
# by visit_date ASCENDING. Each summary has:
#   {
#     "visit_id": str,
#     "visit_date": str (ISO date),
#     "medications_affirmed": list[str],   # normalized lowercase
#     "symptoms_affirmed": list[str],
#     "symptoms_denied": list[str],
#   }
#
# This is exactly the shape the /api/patients/{id}/visits endpoint already
# returns, so the API layer can pass that response straight in.


# --- Detector 1: symptom escalation ------------------------------------------

def detect_symptom_escalation(
    visits: list[dict[str, Any]],
    min_consecutive: int = 3,
) -> list[Finding]:
    """
    Find symptoms affirmed in min_consecutive (default 3) most-recent visits.

    Rationale: a symptom that persists across multiple consecutive recent
    visits is more clinically concerning than one that comes and goes. We
    require the streak to include the most recent visit — a symptom that
    persisted but then resolved is a different (resolution) pattern.

    Severity: moderate by default. High if the streak covers 5+ visits.
    """
    if len(visits) < min_consecutive:
        return []

    findings: list[Finding] = []

    # Collect the set of all symptoms that appear in any recent visit, then
    # check each one for consecutive presence ending at the latest visit.
    all_recent_symptoms: set[str] = set()
    for v in visits[-min_consecutive:]:
        all_recent_symptoms.update(v.get("symptoms_affirmed", []))

    for symptom in sorted(all_recent_symptoms):
        # Walk backwards from latest visit, count consecutive affirmations.
        streak: list[dict[str, Any]] = []
        for v in reversed(visits):
            if symptom in v.get("symptoms_affirmed", []):
                streak.append(v)
            else:
                break

        if len(streak) < min_consecutive:
            continue

        streak.reverse()  # chronological order
        severity: Severity = "high" if len(streak) >= 5 else "moderate"
        first_date = streak[0]["visit_date"]
        latest_date = streak[-1]["visit_date"]

        findings.append(Finding(
            detector="symptom_escalation",
            severity=severity,
            title=f"{symptom.capitalize()} persistent across {len(streak)} consecutive visits",
            summary=(
                f"Affirmed at every visit since {first_date}, including the "
                f"most recent visit on {latest_date}. Persistent symptoms "
                f"warrant follow-up if not already being managed."
            ),
            evidence={
                "entity": symptom,
                "consecutive_visits": len(streak),
                "first_visit_in_streak": first_date,
                "latest_visit": latest_date,
                "visit_dates": [v["visit_date"] for v in streak],
            },
        ))

    return findings


# --- Detector 2: new medication ----------------------------------------------

def detect_new_medications(
    visits: list[dict[str, Any]],
    look_back: int = 1,
) -> list[Finding]:
    """
    Find medications present at the latest visit but absent from all prior
    visits within the patient's record.

    look_back=1 means "compare latest to all earlier visits combined" —
    if a med shows up at the latest visit and was never present before, flag
    it. New prescriptions correlate with diagnostic changes and are worth
    surfacing.

    Severity: low by default. Moderate if 3+ new meds appear simultaneously
    (often signals a meaningful clinical event like a hospitalization or
    procedure).
    """
    if len(visits) < 2:
        return []

    latest = visits[-1]
    earlier_meds: set[str] = set()
    for v in visits[:-1]:
        earlier_meds.update(v.get("medications_affirmed", []))

    latest_meds = set(latest.get("medications_affirmed", []))
    new_meds = sorted(latest_meds - earlier_meds)

    if not new_meds:
        return []

    severity: Severity = "moderate" if len(new_meds) >= 3 else "low"

    return [Finding(
        detector="new_medication",
        severity=severity,
        title=(
            f"{len(new_meds)} new medication{'s' if len(new_meds) > 1 else ''} "
            f"at latest visit"
        ),
        summary=(
            f"The following medication{'s' if len(new_meds) > 1 else ''} "
            f"appeared for the first time at the most recent visit "
            f"({latest['visit_date']}): {', '.join(new_meds)}. "
            "New prescriptions often correlate with diagnostic or treatment changes."
        ),
        evidence={
            "new_medications": new_meds,
            "latest_visit": latest["visit_date"],
            "first_appearance_at_visit": latest["visit_date"],
        },
    )]


# --- Detector 3: drug interaction --------------------------------------------

# Path is relative to the backend container's filesystem. The data/ volume
# mount in docker-compose.yml exposes the host data/ directory at /app/data/.
DRUG_INTERACTIONS_PATH = Path("/app/data/drug_interactions.json")


def _load_drug_interactions() -> list[dict[str, Any]]:
    """Load the curated drug interaction pairs. Returns [] on missing file."""
    if not DRUG_INTERACTIONS_PATH.exists():
        return []
    with DRUG_INTERACTIONS_PATH.open() as f:
        data = json.load(f)
    return data.get("interactions", [])


def detect_drug_interactions(
    visits: list[dict[str, Any]],
) -> list[Finding]:
    """
    Find pairs of currently-active medications matching the curated
    interaction list.

    "Currently active" = present in the latest visit's medications_affirmed.
    A medication negated at the latest visit isn't current. A medication
    historically taken but not at the latest visit isn't current either.

    Severity comes from the JSON entry — does not get re-derived here.
    """
    if not visits:
        return []

    interactions = _load_drug_interactions()
    if not interactions:
        return []

    latest = visits[-1]
    current_meds = set(latest.get("medications_affirmed", []))

    findings: list[Finding] = []
    for interaction in interactions:
        drugs = [d.lower() for d in interaction.get("drugs", [])]
        if len(drugs) < 2:
            continue
        if all(d in current_meds for d in drugs):
            severity = interaction.get("severity", "moderate")
            if severity not in ("low", "moderate", "high"):
                severity = "moderate"

            pair_label = " + ".join(drugs)
            findings.append(Finding(
                detector="drug_interaction",
                severity=severity,  # type: ignore[arg-type]
                title=f"Potential interaction: {pair_label}",
                summary=interaction.get("concern", ""),
                evidence={
                    "drugs": drugs,
                    "category": interaction.get("category"),
                    "current_at_visit": latest["visit_date"],
                },
            ))

    return findings


# --- Aggregator --------------------------------------------------------------

def detect_all(
    visits: list[dict[str, Any]],
) -> list[Finding]:
    """
    Run all detectors and return findings sorted by severity (high first),
    then by detector name for stable ordering.
    """
    findings: list[Finding] = []
    findings.extend(detect_symptom_escalation(visits))
    findings.extend(detect_new_medications(visits))
    findings.extend(detect_drug_interactions(visits))

    severity_rank = {"high": 0, "moderate": 1, "low": 2}
    findings.sort(
        key=lambda f: (severity_rank.get(f.severity, 99), f.detector, f.title)
    )
    return findings
