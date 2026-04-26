# Known Issues and Resolutions

This document tracks retrieval and reasoning issues identified during testing,
along with how they were addressed.

## 1. Temporal-recall failure on "first appearance" queries (PARTIALLY RESOLVED in Week 3)

**Symptom:** Query "When did chest pain first appear in her history?" returns
"the excerpts do not provide information," despite the relevant November 2024
chunk existing in the database.

**Root cause investigation:** Three retrieval configurations tested:

| Configuration | Top-5 contains Nov 2024? | Result |
|---|---|---|
| Bi-encoder only, k=5 | No | Fail |
| Bi-encoder only, k=10 | Yes | Pass |
| Bi-encoder + cross-encoder rerank, candidate pool=20, k=5 | No | Fail |
| Bi-encoder + cross-encoder rerank, candidate pool=50, k=5 | No | Fail |

In the third configuration, the November 2024 chunk was retrieved into the
candidate pool but reranked to position 15. The cross-encoder correctly
identified that other chunks discuss chest pain more intensively, but
"intensity of topical match" is the wrong relevance criterion for "when did
this symptom first appear."

**Conclusion:** Pure dense retrieval — even with high-quality reranking —
cannot reliably answer queries whose semantics depend on chronological
ordering rather than topical density. The cross-encoder is functioning
correctly; the relevance signal it optimizes for does not match the user's
intent for temporal queries.

**Resolution (partial, implemented across Weeks 2 and 3):**

1. *Cross-encoder reranking* (Week 2): Retrieve top-50 candidates via pgvector,
   rerank with `ms-marco-MiniLM-L-6-v2`, return top-5. Improves general retrieval
   quality but does not solve temporal queries — the cross-encoder correctly
   ranks chunks by topical density, which is the wrong relevance signal for
   "first occurrence" questions.

2. *Structured entity layer* (Week 3): scispaCy extracts clinical entities at
   ingestion time into `visit_entities`. Temporal queries can now be answered
   by SQL (`SELECT MIN(visit_date) WHERE entity_type='symptom' AND ...`) rather
   than by retrieval.

3. *Turn-aware negation refinement* (Week 3): Custom post-processing pass that
   handles cross-turn denials negspacy misses (see Finding #5).

**Remaining limitation:** scispaCy's entity granularity sometimes drops
qualifiers — "chest tightness" may be extracted as bare "tightness" — which
breaks `WHERE normalized_text LIKE '%chest%'` filters. The first
patient-affirmed chest mention in Sarah Chen's record is November 2024 by
clinical reading, but is reported as April 2025 by the structured layer
because the November "tightness" entity lacks its "chest" qualifier in the
database. Documented as Finding #6.

**Architectural lesson:** RAG is not a hammer for every query type. Narrative
questions ("how have things changed?") need semantic retrieval; structured
questions ("what was first?", "what's the current list?") need structured data.
The hybrid approach is not optional — it's the architecture.

## 2. Incomplete medication synthesis (PARTIALLY RESOLVED in Week 3)

**Symptom:** Query "What medications is Sarah Chen currently taking?" returned
only lisinopril and omeprazole, despite the most recent visit transcript
listing six concurrent medications.

**Root cause:** Comma-separated medication lists embedded in conversational
prose get split across chunk boundaries, and the resulting fragments lose
context. The LLM discounts fragmented evidence relative to clearly-stated
single-medication mentions.

**Resolution:** Clinical entity extraction (scispaCy) at ingestion time produces
a structured `visit_entities` table with per-visit medication lists. Fact-list
queries can be served from structured data; narrative queries continue to use
RAG. This addresses the synthesis problem at the source.

## 5. Cross-turn negation misattribution (PARTIALLY RESOLVED in Week 3)

**Symptom:** Entities mentioned in a doctor's question and denied by the
patient in the next turn (e.g., "Doctor: Any chest pain? Patient: Um, no,
not really.") were extracted with `negated=false`. negspacy operates within a
single sentence/clause and does not bridge speaker turns.

**Concrete impact (before fix):** Sarah Chen's 2024-09-15 visit recorded
`chest pain | negated=false` despite the patient explicitly denying chest pain
in the conversation. This produced false positives for "first occurrence"
queries — the structured layer would return September 2024 as the first chest
pain mention when in fact Sarah denied it at that visit.

**Resolution (implemented):** Added `_apply_turn_aware_negation` post-processing
pass in `core/entities.py`. The pass:
- Splits transcripts into ordered turns by `Doctor:` / `Patient:` markers
- For each entity in a doctor's turn, examines the immediately following
  patient turn
- If the patient turn opens with denial language (`no`, `not really`,
  `haven't`, `don't`, `none`, `nothing`, `deny`), the entity is marked
  `negated=true`
- Tagged with `negation_source: "turn_aware_denial"` in the entity's `extra`
  field for auditability
- Only escalates `False → True`; never overrides negspacy's `True` results

**Verification:** After re-ingestion, the 2024-09-15 chest pain entity
correctly shows `negated=true`. Verified across the patient's full record;
no regressions on previously-correct negations.

**Caveat — over-negation on compound doctor questions:** When a doctor asks a
multi-clause question like "the chest heaviness — do you notice it in your
jaw, shoulder, or back?" and the patient responds "No, just the chest itself,"
the heuristic marks `chest heaviness` as negated even though the patient is
denying *radiation*, not the chest heaviness itself. This is a known false
positive of the cross-turn heuristic. In Sarah's record, this affects the
2025-01-20 `chest heaviness` entity. Properly resolving this requires
question-parsing — distinguishing what the doctor is actually asking — which
is beyond regex/heuristic scope. A future LLM-based refinement pass could
address it.

## 6. Entity granularity loss in scispaCy extraction (KNOWN LIMITATION)

**Symptom:** scispaCy's `en_ner_bc5cdr_md` model sometimes extracts symptom
spans without their anatomical or descriptive qualifiers. "Chest tightness"
in the November 2024 visit was extracted as three separate single-word
entities: `tightness`, `pain`, `heaviness`. None of these match
`WHERE normalized_text LIKE '%chest%'` filters.

**Concrete impact:** The structured layer's "first chest pain occurrence"
query returns April 2025 as the earliest patient-affirmed chest mention,
because the November 2024 mention is in the database under bare entity names
that don't include "chest." A clinician reading the record would identify
November 2024 as the first mention.

**Decision:** Accept the limitation. Improving extraction granularity
requires either a different NER model (e.g., a UMLS-linked extractor that
captures multi-word clinical concepts) or LLM-based entity refinement (a
post-processing pass where GPT-4o-mini cleans and merges scispaCy's raw
spans). Both are out of scope for the current project phase.

**Future work:** A hybrid LLM-refinement pass would address Findings #5
(over-negation) and #6 (granularity) simultaneously, by re-examining
scispaCy's raw output against the full transcript context. This is the
correct production architecture for clinical NLP — symbolic extractor for
recall, LLM for precision — but adds ~$0.01 per visit in API cost and
~60-90 minutes of implementation time.

