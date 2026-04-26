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

# Patterns that indicate the patient is denying what was just asked.
# Matched only at the start of a patient turn (first ~120 chars).
TURN_DENIAL_PATTERNS = [
    re.compile(r"^\s*(um,?\s+)?no\b", re.I),
    re.compile(r"^\s*(um,?\s+)?nope\b", re.I),
    re.compile(r"^\s*not\s+really\b", re.I),
    re.compile(r"^\s*(i\s+)?haven['’]?t\b", re.I),
    re.compile(r"^\s*(i\s+)?don['’]?t\b", re.I),
    re.compile(r"^\s*(i\s+)?didn['’]?t\b", re.I),
    re.compile(r"^\s*none\b", re.I),
    re.compile(r"^\s*nothing\b", re.I),
    re.compile(r"^\s*(i\s+)?deny\b", re.I),
]

# Speaker tag patterns (Doctor: ... Patient: ...).
SPEAKER_TAG = re.compile(r"^\s*(Doctor|Patient|Dr\.?|Pt\.?)\s*:\s*", re.I)


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


@dataclass
class Turn:
    speaker: str  # "doctor" or "patient" or "unknown"
    text: str
    char_start: int
    char_end: int


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


def _split_into_turns(text: str) -> list[Turn]:
    """
    Split a transcript with 'Doctor:' / 'Patient:' speaker tags into ordered turns.

    A turn runs from one speaker tag to the next. Char offsets refer to the
    full transcript so we can correlate entities back to their containing turn.
    """
    turns: list[Turn] = []
    matches = list(re.finditer(r"^\s*(Doctor|Patient|Dr\.?|Pt\.?)\s*:\s*", text, re.I | re.MULTILINE))

    if not matches:
        return [Turn(speaker="unknown", text=text, char_start=0, char_end=len(text))]

    for i, match in enumerate(matches):
        speaker_raw = match.group(1).lower()
        speaker = "doctor" if speaker_raw.startswith(("d", "dr")) else "patient"
        content_start = match.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        turns.append(
            Turn(
                speaker=speaker,
                text=text[content_start:content_end],
                char_start=content_start,
                char_end=content_end,
            )
        )

    return turns


def _find_turn_for_position(turns: list[Turn], pos: int) -> int | None:
    """Return index into `turns` of the turn containing `pos`, or None."""
    for i, t in enumerate(turns):
        if t.char_start <= pos < t.char_end:
            return i
    return None


def _next_patient_turn(turns: list[Turn], from_idx: int) -> Turn | None:
    """Find the next patient turn after `from_idx`."""
    for t in turns[from_idx + 1:]:
        if t.speaker == "patient":
            return t
    return None


def _is_denial_response(patient_turn_text: str, scan_chars: int = 120) -> bool:
    """Check if a patient turn opens with denial language."""
    head = patient_turn_text[:scan_chars]
    return any(p.search(head) for p in TURN_DENIAL_PATTERNS)


def _apply_turn_aware_negation(
    entities: list[ClinicalEntity],
    transcript: str,
) -> list[ClinicalEntity]:
    """
    Augment negspacy's negation flags with cross-turn denial detection.

    Rule: if an entity sits in a doctor's turn and the immediately following
    patient turn starts with denial language ("no", "not really", "haven't",
    etc.), mark the entity as negated. We never flip a True from negspacy
    back to False — this only escalates missed negations, not overrides.
    """
    turns = _split_into_turns(transcript)
    if len(turns) <= 1:
        return entities

    updated: list[ClinicalEntity] = []
    for ent in entities:
        if ent.negated or ent.char_start is None:
            updated.append(ent)
            continue

        turn_idx = _find_turn_for_position(turns, ent.char_start)
        if turn_idx is None or turns[turn_idx].speaker != "doctor":
            updated.append(ent)
            continue

        next_pt = _next_patient_turn(turns, turn_idx)
        if next_pt is None:
            updated.append(ent)
            continue

        if _is_denial_response(next_pt.text):
            ent.negated = True
            ent.extra = {**ent.extra, "negation_source": "turn_aware_denial"}

        updated.append(ent)

    return updated


def _deduplicate_overlapping(entities: list[ClinicalEntity]) -> list[ClinicalEntity]:
    """Prefer shorter, more atomic spans when scispaCy emits overlapping entities."""
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

    refined = _apply_turn_aware_negation(raw_entities, text)
    return _deduplicate_overlapping(refined)
