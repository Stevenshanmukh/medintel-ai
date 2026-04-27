from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.temporal_resolver import resolve_anchor, get_previous_visit, ResolvedAnchor



SUBJECT_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "with",
    "her", "his", "their", "patient", "patients", "and", "or",
}


def _subject_to_pattern(subject: str) -> str:
    """
    Convert a classifier-extracted subject phrase into a SQL ILIKE pattern.

    Strategy: pick the longest non-stopword token from the subject. This makes
    'chest pain' match 'chest tightness', 'shortness of breath' match 'breath',
    etc. — which works because the structured layer's entity_text often uses
    a related but non-identical phrase.
    """
    tokens = [t.strip().lower() for t in subject.split() if t.strip()]
    candidates = [t for t in tokens if len(t) > 3 and t not in SUBJECT_STOPWORDS]
    if not candidates:
        candidates = tokens or [subject.lower()]
    keyword = max(candidates, key=len)
    return f"%{keyword}%"


COMMON_MEDICATIONS = {
    # Cardiovascular
    "lisinopril", "atorvastatin", "metoprolol", "aspirin", "clopidogrel",
    "nitroglycerin", "amlodipine", "losartan", "rosuvastatin", "simvastatin",
    "pravastatin", "warfarin", "apixaban", "rivaroxaban", "dabigatran",
    "carvedilol", "bisoprolol", "propranolol", "diltiazem", "verapamil",
    "hydrochlorothiazide", "furosemide", "spironolactone", "ramipril",
    "enalapril", "valsartan", "olmesartan",
    # GI
    "omeprazole", "pantoprazole", "esomeprazole", "ranitidine", "famotidine",
    # Diabetes
    "metformin", "insulin", "glipizide", "sitagliptin", "empagliflozin",
    "liraglutide", "semaglutide",
    # Pain / NSAIDs
    "ibuprofen", "acetaminophen", "naproxen", "tramadol",
    # Mental health
    "sertraline", "escitalopram", "citalopram", "fluoxetine", "venlafaxine",
    "bupropion", "trazodone",
    # Common others
    "levothyroxine", "albuterol", "fluticasone", "montelukast", "prednisone",
    "amoxicillin", "azithromycin", "ciprofloxacin", "doxycycline",
}


def _is_real_medication(entity_text: str) -> bool:
    """Check if an extracted entity is a real medication, not a chemical/lab/lifestyle term."""
    return entity_text.strip().lower() in COMMON_MEDICATIONS


@dataclass
class StructuredAnswer:
    """A structured-path query result with the same shape as RAG answers."""
    answer: str
    evidence_rows: list[dict]
    sql_used: str


def _patient_filter_clause() -> str:
    return "AND v.patient_id = CAST(:patient_id AS uuid)"


def get_current_medications(db: Session, patient_id: UUID) -> StructuredAnswer:
    """Return the patient's most recently affirmed medications.

    'Current' means: any medication mentioned in the most recent visit where it
    appears, where the latest mention was not negated. Medications negated in
    later visits are excluded.
    """
    sql = """
        WITH latest_per_med AS (
            SELECT
                ve.normalized_text,
                ve.entity_text,
                ve.negated,
                v.visit_date::date AS last_visit,
                ROW_NUMBER() OVER (
                    PARTITION BY ve.normalized_text
                    ORDER BY v.visit_date DESC
                ) AS rn
            FROM visit_entities ve
            JOIN visits v ON v.id = ve.visit_id
            WHERE ve.entity_type = 'medication'
              AND v.patient_id = CAST(:patient_id AS uuid)
        )
        SELECT normalized_text, entity_text, last_visit
        FROM latest_per_med
        WHERE rn = 1 AND negated = false
        ORDER BY normalized_text
    """

    rows = db.execute(text(sql), {"patient_id": str(patient_id)}).mappings().all()

    # Note: scispaCy's CHEMICAL label is broader than "prescription medication" —
    # it labels alcohol, cholesterol, GERD, lab values, and chemical class names
    # as CHEMICAL. We post-filter against a curated common-medication list rather
    # than relying on the NER label alone. For production, this list would be
    # replaced with an RxNorm lookup. Documented as a project-scope decision.
    rows = [r for r in rows if _is_real_medication(r["normalized_text"])]

    if not rows:
        return StructuredAnswer(
            answer="No medications found in this patient's structured record.",
            evidence_rows=[],
            sql_used=sql,
        )

    med_lines = [
        f"- {row['entity_text']} (last mentioned {row['last_visit']})"
        for row in rows
    ]
    answer = (
        f"Based on the structured clinical record, the patient has "
        f"{len(rows)} affirmed medication{'s' if len(rows) != 1 else ''} on file:\n\n"
        + "\n".join(med_lines)
    )

    return StructuredAnswer(
        answer=answer,
        evidence_rows=[dict(r) for r in rows],
        sql_used=sql,
    )


def get_first_occurrence(
    db: Session, patient_id: UUID, subject: str
) -> StructuredAnswer:
    """Return the earliest non-negated mention of a symptom or condition."""
    sql = """
        SELECT
            v.visit_date::date AS visit_date,
            ve.entity_text,
            ve.normalized_text,
            v.id AS visit_id
        FROM visit_entities ve
        JOIN visits v ON v.id = ve.visit_id
        WHERE ve.entity_type = 'symptom'
          AND ve.negated = false
          AND ve.normalized_text ILIKE :pattern
          AND v.patient_id = CAST(:patient_id AS uuid)
        ORDER BY v.visit_date ASC
        LIMIT 1
    """

    pattern = _subject_to_pattern(subject)
    row = db.execute(
        text(sql),
        {"patient_id": str(patient_id), "pattern": pattern},
    ).mappings().first()

    if not row:
        return StructuredAnswer(
            answer=(
                f"No affirmed mentions of '{subject}' were found in the patient's "
                f"structured symptom record. Note that the structured record may "
                f"miss mentions where the entity was extracted without its "
                f"qualifier (see project documentation, Finding #6)."
            ),
            evidence_rows=[],
            sql_used=sql,
        )

    answer = (
        f"Based on the structured record, the first affirmed mention of "
        f"'{subject}' was on {row['visit_date']} (recorded as "
        f"\"{row['entity_text']}\")."
    )

    return StructuredAnswer(
        answer=answer,
        evidence_rows=[dict(row)],
        sql_used=sql,
    )


def get_all_mentions(
    db: Session, patient_id: UUID, subject: str
) -> StructuredAnswer:
    """Return every visit where a given symptom/medication was affirmed."""
    sql = """
        SELECT
            v.visit_date::date AS visit_date,
            ve.entity_type,
            ve.entity_text,
            ve.negated
        FROM visit_entities ve
        JOIN visits v ON v.id = ve.visit_id
        WHERE ve.normalized_text ILIKE :pattern
          AND v.patient_id = CAST(:patient_id AS uuid)
        ORDER BY v.visit_date ASC
    """

    pattern = _subject_to_pattern(subject)
    rows = db.execute(
        text(sql),
        {"patient_id": str(patient_id), "pattern": pattern},
    ).mappings().all()

    if not rows:
        return StructuredAnswer(
            answer=f"No mentions of '{subject}' found in the structured record.",
            evidence_rows=[],
            sql_used=sql,
        )

    affirmed = [r for r in rows if not r["negated"]]
    denied = [r for r in rows if r["negated"]]

    lines = [
        f"Found {len(rows)} mention{'s' if len(rows) != 1 else ''} of "
        f"'{subject}' in the structured record:"
    ]
    if affirmed:
        lines.append(f"\nAffirmed ({len(affirmed)}):")
        lines.extend(
            f"  - {r['visit_date']}: {r['entity_text']} ({r['entity_type']})"
            for r in affirmed
        )
    if denied:
        lines.append(f"\nDenied or negated ({len(denied)}):")
        lines.extend(
            f"  - {r['visit_date']}: {r['entity_text']} ({r['entity_type']})"
            for r in denied
        )

    return StructuredAnswer(
        answer="\n".join(lines),
        evidence_rows=[dict(r) for r in rows],
        sql_used=sql,
    )


def get_unsafe_response() -> StructuredAnswer:
    """Standard response for medical advice, treatment recommendations, etc."""
    return StructuredAnswer(
        answer=(
            "This question asks for clinical judgment or information that may "
            "not be in the visit record. I can summarize what the record "
            "contains, but I cannot make diagnoses, treatment recommendations, "
            "or supply information not documented in the visits. Please "
            "consult a clinician for medical decisions."
        ),
        evidence_rows=[],
        sql_used="",
    )


def _get_visit_entities(
    db: Session,
    visit_id: UUID,
    subject_pattern: str | None = None,
) -> dict:
    """
    Pull all entities for a single visit, organized for diffing.

    If subject_pattern is provided, narrows results to entities whose
    normalized_text matches (ILIKE %pattern%). Subject filtering uses
    the same pattern logic as first_occurrence.

    Returns:
        {
            "medications": set of normalized medication names (affirmed only),
            "affirmed_symptoms": set of normalized symptom texts,
            "raw_rows": list of dicts for evidence display,
        }

    Medications are filtered against COMMON_MEDICATIONS (same rule as
    get_current_medications) to drop scispaCy CHEMICAL false positives.
    """
    if subject_pattern:
        sql = """
            SELECT
                entity_type,
                entity_text,
                normalized_text,
                negated,
                severity
            FROM visit_entities
            WHERE visit_id = CAST(:visit_id AS uuid)
              AND normalized_text ILIKE :pattern
            ORDER BY entity_type, normalized_text
        """
        params = {"visit_id": str(visit_id), "pattern": f"%{subject_pattern}%"}
    else:
        sql = """
            SELECT
                entity_type,
                entity_text,
                normalized_text,
                negated,
                severity
            FROM visit_entities
            WHERE visit_id = CAST(:visit_id AS uuid)
            ORDER BY entity_type, normalized_text
        """
        params = {"visit_id": str(visit_id)}

    rows = db.execute(text(sql), params).mappings().all()
    rows = [dict(r) for r in rows]

    medications = {
        r["normalized_text"]
        for r in rows
        if r["entity_type"] == "medication"
        and not r["negated"]
        and _is_real_medication(r["normalized_text"])
    }

    affirmed_symptoms = {
        r["normalized_text"]
        for r in rows
        if r["entity_type"] == "symptom" and not r["negated"]
    }

    return {
        "medications": medications,
        "affirmed_symptoms": affirmed_symptoms,
        "raw_rows": rows,
    }


def _format_anchor_label(anchor: ResolvedAnchor) -> str:
    """Human-readable label for a resolved visit, used in the answer text."""
    return f"visit {anchor.visit_number} ({anchor.visit_date.isoformat()})"


def compare_visits(
    db: Session,
    patient_id: UUID,
    anchor_a_phrase: str | None,
    anchor_b_phrase: str | None,
    subject: str | None = None,
) -> StructuredAnswer:
    """
    Diff two visits across medications and affirmed symptoms.

    Resolution rules:
      - anchor_a_phrase must resolve. If not, return polite refusal.
      - If anchor_b_phrase is None, use the visit immediately before anchor_a
        (implicit compare-to-previous).
      - If anchor_a is the first visit and anchor_b is None, refuse politely
        (nothing to compare against).

    Subject filter:
      - If subject is non-null, results are narrowed to entities whose
        normalized_text matches the subject pattern. Otherwise, the full
        diff (all medications and all affirmed symptoms) is returned.
    """
    anchor_a = resolve_anchor(db, patient_id, anchor_a_phrase)
    if anchor_a is None:
        return StructuredAnswer(
            answer=(
                f"I couldn't identify which visit you meant by '{anchor_a_phrase}'. "
                "Try phrasing it as 'first visit', 'most recent visit', "
                "'visit 3', or an explicit date like 'April 2025'."
            ),
            evidence_rows=[],
            sql_used="",
        )

    if anchor_b_phrase:
        anchor_b = resolve_anchor(db, patient_id, anchor_b_phrase)
        if anchor_b is None:
            return StructuredAnswer(
                answer=(
                    f"I identified the first visit ({_format_anchor_label(anchor_a)}) "
                    f"but couldn't resolve '{anchor_b_phrase}'. "
                    "Try a phrase like 'first visit', 'last visit', or 'April 2025'."
                ),
                evidence_rows=[],
                sql_used="",
            )
    else:
        anchor_b = get_previous_visit(db, patient_id, anchor_a.visit_id)
        if anchor_b is None:
            return StructuredAnswer(
                answer=(
                    f"You asked about {_format_anchor_label(anchor_a)}, but there's "
                    "no earlier visit to compare against (this is the first visit "
                    "in the record)."
                ),
                evidence_rows=[],
                sql_used="",
            )

    # Always order so anchor_a is the earlier visit.
    if anchor_a.visit_date > anchor_b.visit_date:
        anchor_a, anchor_b = anchor_b, anchor_a

    # Apply subject filter via existing pattern helper.
    subject_pattern = _subject_to_pattern(subject) if subject else None

    data_a = _get_visit_entities(db, anchor_a.visit_id, subject_pattern)
    data_b = _get_visit_entities(db, anchor_b.visit_id, subject_pattern)

    added_meds = sorted(data_b["medications"] - data_a["medications"])
    removed_meds = sorted(data_a["medications"] - data_b["medications"])
    persistent_meds = sorted(data_a["medications"] & data_b["medications"])

    new_symptoms = sorted(data_b["affirmed_symptoms"] - data_a["affirmed_symptoms"])
    resolved_symptoms = sorted(data_a["affirmed_symptoms"] - data_b["affirmed_symptoms"])
    persistent_symptoms = sorted(
        data_a["affirmed_symptoms"] & data_b["affirmed_symptoms"]
    )

    label_a = _format_anchor_label(anchor_a)
    label_b = _format_anchor_label(anchor_b)

    # Header line varies based on whether subject filter is active.
    if subject:
        header = (
            f"Comparing '{subject}'-related changes between {label_a} and {label_b}:"
        )
    else:
        header = f"Comparing {label_a} to {label_b}:"

    lines = [header, ""]
    lines.append("Medications:")
    lines.append(
        f"  - Added in {label_b}: "
        f"{', '.join(added_meds) if added_meds else 'none'}"
    )
    lines.append(
        f"  - Removed by {label_b}: "
        f"{', '.join(removed_meds) if removed_meds else 'none'}"
    )
    lines.append(
        f"  - Persistent (in both): "
        f"{', '.join(persistent_meds) if persistent_meds else 'none'}"
    )
    lines.append("")
    lines.append("Affirmed symptoms:")
    lines.append(
        f"  - New in {label_b}: "
        f"{', '.join(new_symptoms) if new_symptoms else 'none'}"
    )
    lines.append(
        f"  - Resolved by {label_b}: "
        f"{', '.join(resolved_symptoms) if resolved_symptoms else 'none'}"
    )
    lines.append(
        f"  - Persistent: "
        f"{', '.join(persistent_symptoms) if persistent_symptoms else 'none'}"
    )

    if subject and not (
        added_meds or removed_meds or new_symptoms or resolved_symptoms
        or persistent_meds or persistent_symptoms
    ):
        lines.append("")
        lines.append(
            f"(No entities matching '{subject}' were found in either visit. "
            "If this is unexpected, try rephrasing — e.g. 'chest' instead of "
            "'chest pain' — or remove the subject to see the full diff.)"
        )

    # Evidence rows: a flat list the frontend can render. Each row tags which
    # visit it came from and how it appeared in the diff.
    evidence_rows = []
    for med in added_meds:
        evidence_rows.append({
            "category": "medication",
            "diff_status": "added",
            "name": med,
            "visit_a": anchor_a.visit_date.isoformat(),
            "visit_b": anchor_b.visit_date.isoformat(),
        })
    for med in removed_meds:
        evidence_rows.append({
            "category": "medication",
            "diff_status": "removed",
            "name": med,
            "visit_a": anchor_a.visit_date.isoformat(),
            "visit_b": anchor_b.visit_date.isoformat(),
        })
    for sym in new_symptoms:
        evidence_rows.append({
            "category": "symptom",
            "diff_status": "new",
            "name": sym,
            "visit_a": anchor_a.visit_date.isoformat(),
            "visit_b": anchor_b.visit_date.isoformat(),
        })
    for sym in resolved_symptoms:
        evidence_rows.append({
            "category": "symptom",
            "diff_status": "resolved",
            "name": sym,
            "visit_a": anchor_a.visit_date.isoformat(),
            "visit_b": anchor_b.visit_date.isoformat(),
        })

    return StructuredAnswer(
        answer="\n".join(lines),
        evidence_rows=evidence_rows,
        sql_used="see _get_visit_entities; two queries, one per visit",
    )


def trend_over_time(
    db: Session,
    patient_id: UUID,
    subject: str | None,
) -> StructuredAnswer:
    """
    Return an ordered series showing how a single subject (symptom or medication)
    appears across all visits in chronological order.

    For each visit, returns:
      - present: True if the subject is affirmed at that visit
      - status: 'affirmed' | 'denied' | 'absent'
      - severity: severity tag if available (often null per Finding #4)
      - matched_entities: list of entity_text values that matched the pattern

    A subject is required. If subject is None, returns a polite refusal — trends
    require something specific to trend.
    """
    if not subject:
        return StructuredAnswer(
            answer=(
                "Trend queries need a specific subject to track — for example, "
                "'How has her chest pain progressed?' or 'Show the trajectory "
                "of her shortness of breath.' Without a subject, I can't build "
                "a series. Try a broader narrative question instead."
            ),
            evidence_rows=[],
            sql_used="",
        )

    pattern = _subject_to_pattern(subject)

    # One query, all visits, with the entities for this subject left-joined.
    # GROUP BY at the visit level so we get one row per visit even when
    # multiple matching entities appear.
    sql = """
        SELECT
            v.id AS visit_id,
            v.visit_date::date AS visit_date,
            v.chief_complaint,
            COALESCE(
                BOOL_OR(ve.negated = false), false
            ) AS any_affirmed,
            COALESCE(
                BOOL_OR(ve.negated = true), false
            ) AS any_negated,
            ARRAY_AGG(
                DISTINCT ve.entity_text
                ORDER BY ve.entity_text
            ) FILTER (WHERE ve.entity_text IS NOT NULL) AS matched_entities,
            ARRAY_AGG(
                DISTINCT ve.severity
                ORDER BY ve.severity
            ) FILTER (WHERE ve.severity IS NOT NULL) AS severities
        FROM visits v
        LEFT JOIN visit_entities ve
          ON ve.visit_id = v.id
         AND ve.normalized_text ILIKE :pattern
        WHERE v.patient_id = CAST(:patient_id AS uuid)
        GROUP BY v.id, v.visit_date, v.chief_complaint
        ORDER BY v.visit_date
    """

    rows = db.execute(
        text(sql),
        {"patient_id": str(patient_id), "pattern": f"%{pattern}%"},
    ).mappings().all()
    rows = [dict(r) for r in rows]

    if not rows:
        return StructuredAnswer(
            answer=f"No visits found for this patient.",
            evidence_rows=[],
            sql_used=sql,
        )

    # Build the series. status precedence: affirmed > denied > absent.
    series = []
    for r in rows:
        if r["any_affirmed"]:
            status = "affirmed"
            present = True
        elif r["any_negated"]:
            status = "denied"
            present = False
        else:
            status = "absent"
            present = False

        severity_list = r["severities"] or []
        severity = severity_list[0] if severity_list else None

        series.append({
            "visit_id": str(r["visit_id"]),
            "visit_date": r["visit_date"].isoformat(),
            "chief_complaint": r["chief_complaint"],
            "present": present,
            "status": status,
            "severity": severity,
            "matched_entities": r["matched_entities"] or [],
        })

    affirmed_count = sum(1 for s in series if s["status"] == "affirmed")
    denied_count = sum(1 for s in series if s["status"] == "denied")
    absent_count = sum(1 for s in series if s["status"] == "absent")

    lines = [
        f"Trajectory of '{subject}' across {len(series)} visits "
        f"({affirmed_count} affirmed, {denied_count} denied, {absent_count} absent):"
    ]
    lines.append("")
    for s in series:
        severity_str = f" [{s['severity']}]" if s["severity"] else ""
        if s["status"] == "affirmed":
            entities_str = ", ".join(s["matched_entities"])
            lines.append(f"  ✓ {s['visit_date']}: {entities_str}{severity_str}")
        elif s["status"] == "denied":
            entities_str = ", ".join(s["matched_entities"])
            lines.append(f"  ✗ {s['visit_date']}: denied ({entities_str})")
        else:
            lines.append(f"  · {s['visit_date']}: —")

    # Finding #6 surface: warn when chief complaint mentions a chest-keyword
    # but no entity was extracted at the chunk level. Limited to chest queries
    # for now since that's where the issue manifests in this dataset.
    if "chest" in subject.lower():
        likely_missed = [
            s for s in series
            if s["status"] == "absent"
            and s["chief_complaint"]
            and "chest" in s["chief_complaint"].lower()
        ]
        if likely_missed:
            lines.append("")
            lines.append(
                f"Note: {len(likely_missed)} visit(s) had a chief complaint "
                f"mentioning chest symptoms but no chest-related entity was "
                f"extracted at the chunk level (known limitation, Finding #6 "
                f"in docs/known-issues-and-resolutions.md). Visits affected: "
                f"{', '.join(s['visit_date'] for s in likely_missed)}. "
                f"The trajectory may underreport early mentions."
            )

    if affirmed_count == 0 and denied_count == 0:

        lines.append("")
        lines.append(
            f"(No mentions of '{subject}' found in any visit. If this is "
            f"unexpected, the entity may have been extracted under a different "
            f"phrase — try a broader subject like just the head noun.)"
        )

    return StructuredAnswer(
        answer="\n".join(lines),
        evidence_rows=series,
        sql_used=sql,
    )


