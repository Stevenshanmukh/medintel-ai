from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


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
