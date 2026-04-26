import re
from dataclasses import dataclass, field
from functools import lru_cache

import spacy
from negspacy.negation import Negex  # noqa: F401  (registered via add_pipe)


SCISPACY_MODEL = "en_ner_bc5cdr_md"

LABEL_TO_TYPE = {
    "DISEASE": "symptom",
    "CHEMICAL": "medication",
}

SEVERITY_PATTERNS = [
    (re.compile(r"\b(severe|severely)\b", re.I), "severe"),
    (re.compile(r"\b(moderate|moderately)\b", re.I), "moderate"),
    (re.compile(r"\b(mild|mildly|slight|slightly|minor)\b", re.I), "mild"),
]

DURATION_PATTERN = re.compile(
    r"\b(?:for|since|over|past|last)\s+"
    r"(?:a\s+)?"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|few|several|couple\s+of)\s+"
    r"(?:second|minute|hour|day|week|month|year)s?"
    r"(?:\s+ago)?",
    re.I,
)


@dataclass
class ClinicalEntity:
    entity_type: str
    entity_text: str
    normalized_text: str
    negated: bool
    severity: str | None = None
    duration: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    confidence: float | None = None
    extra: dict = field(default_factory=dict)


@lru_cache(maxsize=1)
def get_clinical_nlp():
    nlp = spacy.load(SCISPACY_MODEL)
    if "negex" not in nlp.pipe_names:
        nlp.add_pipe("negex", config={"chunk_prefix": ["no", "denies", "denied", "without"]})
    return nlp


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _local_context(text: str, start: int, end: int, window: int = 60) -> str:
    return text[max(0, start - window):min(len(text), end + window)]


def _detect_severity(context: str) -> str | None:
    for pattern, label in SEVERITY_PATTERNS:
        if pattern.search(context):
            return label
    return None


def _detect_duration(context: str) -> str | None:
    match = DURATION_PATTERN.search(context)
    return match.group(0) if match else None


def _deduplicate_overlapping(entities: list[ClinicalEntity]) -> list[ClinicalEntity]:
    """When scispaCy emits overlapping spans (e.g. 'nausea' and 'nausea or shortness of breath'),
    prefer the shorter, more atomic mentions. They're more useful for filtering and storage."""
    if len(entities) <= 1:
        return entities

    sorted_ents = sorted(
        entities,
        key=lambda e: (
            e.char_start if e.char_start is not None else 0,
            -(e.char_end - e.char_start) if e.char_start is not None and e.char_end is not None else 0,
        ),
    )

    keep: list[ClinicalEntity] = []
    for ent in sorted_ents:
        if ent.char_start is None or ent.char_end is None:
            keep.append(ent)
            continue

        overlaps_existing = False
        for existing in keep:
            if existing.char_start is None or existing.char_end is None:
                continue
            if ent.char_start < existing.char_end and ent.char_end > existing.char_start:
                ent_len = ent.char_end - ent.char_start
                ex_len = existing.char_end - existing.char_start
                if ent_len >= ex_len:
                    overlaps_existing = True
                    break

        if not overlaps_existing:
            keep.append(ent)

    return keep


def extract_entities(text: str) -> list[ClinicalEntity]:
    if not text or not text.strip():
        return []

    nlp = get_clinical_nlp()
    doc = nlp(text)

    raw_entities: list[ClinicalEntity] = []

    for ent in doc.ents:
        entity_type = LABEL_TO_TYPE.get(ent.label_)
        if entity_type is None:
            continue

        is_negated = bool(getattr(ent._, "negex", False))
        context = _local_context(text, ent.start_char, ent.end_char)

        raw_entities.append(
            ClinicalEntity(
                entity_type=entity_type,
                entity_text=ent.text,
                normalized_text=_normalize(ent.text),
                negated=is_negated,
                severity=_detect_severity(context) if entity_type == "symptom" else None,
                duration=_detect_duration(context) if entity_type == "symptom" else None,
                char_start=ent.start_char,
                char_end=ent.end_char,
                confidence=None,
                extra={"raw_label": ent.label_},
            )
        )

    return _deduplicate_overlapping(raw_entities)
