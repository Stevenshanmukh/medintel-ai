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

## 7. Finding #6 cascade in longitudinal reasoning (KNOWN LIMITATION)

**Symptom:** Subject-filtered comparisons (e.g., "compare her chest pain between visit 1 and visit 8") inherit the entity-granularity limitation. Visits where qualifiers were dropped during NER will be undercounted in filtered diffs.

**Resolution (automated warning):** The `trend_over_time` handler now includes a self-aware detection pass that checks the visit-level chief complaints. If a visit is reported as `absent` for the subject but the chief complaint contains the keyword (e.g., "chest"), the handler appends a one-line warning note flagging the specific visits where the trajectory may be underreporting mentions. The `compare_visits` handler does not currently include this automated check but is subject to the same underlying limitation.

## 8. Loss of ambient state and qualifiers in NER (Finding #7)

**Symptom:** Entities mentioned as "past history" or medications taken "continuously" are sometimes mischaracterized or missed in per-visit extraction. 
- **Example A:** Sarah Chen has "heart disease" affirmed at Visit 1, despite having no cardiac history at that time (she was being screened for it). NER extracted the mention but lost the "screen for" qualifier.
- **Example B:** `lisinopril` is missing from the structured record for Visits 2 and 5, even though the patient remained on the medication throughout her care. At those visits, the drug was not explicitly mentioned by name in the transcript (it was ambient state), so the per-mention extractor missed it.

**Root Cause:** This is the same root cause as Finding #6 — entity extraction is performed turn-by-turn or mention-by-mention and loses the surrounding qualifiers ("history of," "screening for") as well as the "ambient state" of the patient's record.

**Resolution:** Documented, not fixed. The project accepts that the structured layer is a "mention-based timeline," not a "reconciled medical record." Interestingly, the timeline UI surfaces these gaps visually (e.g., a medication badge disappearing and reappearing), which serves as a prompt for the clinician to verify the record rather than trusting a potentially halluncinated "reconciled" view. Addressable in the future via the same LLM-refinement pass proposed for Finding #6.

## 9. Zero-finding result on "new medication" detector (Sarah Chen)

**Symptom:** The `new_medication` detector returns zero findings for Sarah Chen at Visit 8, even though her medication regimen visibly changed during the arc (adding aspirin, atorvastatin, clopidogrel, metoprolol, and omeprazole post-stent).

**Design Choice:** The detector defines "new" as "first-ever appearance in the patient's longitudinal record."
- For Sarah Chen, all the "post-stent" medications appeared earlier in her record (Visit 6 or 7) before the most recent visit (Visit 8). 
- Thus, at Visit 8, they are "ongoing," not "new."
- The detector correctly identifies that no medications appeared *for the first time ever* at Visit 8.

**Rationale for "new ever" vs "new since last visit":**
A detector that flags any delta between adjacent visits would be noisier due to **Finding #7** (extraction-state inconsistency). For example, `lisinopril` is missing from the extraction history for Visits 2 and 5. An adjacent-visit detector would incorrectly flag `lisinopril` as a "new medication" at Visits 3 and 6 when it was actually ambient state. By looking at the entire prior history, the "new ever" detector is robust to these extraction gaps — if a med was ever seen before, it's not "new."

**Future work:** A more sophisticated "regimen change" detector would identify significant shifts in the active list (e.g., the transition from 1 to 6 medications) by looking at temporal clusters of appearances. This requires the same LLM-based refinement pass proposed for Finding #6 to distinguish between "mention gap" and "discontinuation."

## 10. Dashboard medication source: Latest-visit vs. Longitudinal windowing

**Design Decision:** The dashboard's "Current medications" card displays entities from the `latest_visit` only, rather than the `current_medications` window function (which looks back several months to capture medications mentioned as "ongoing").

**Rationale:**
1. **Clinical Convention:** Clinicians often scan the latest encounter note as the "source of truth" for the current status. Using the latest visit's `medications_affirmed` list matches this mental model and ensures the dashboard is fast (no cross-visit join required for the summary card).
2. **Robustness to Extraction Gaps:** The longitudinal window function is more susceptible to **Finding #8** (over-accumulation of ambient state). If a medication is extracted once and then never mentioned again, the window function might continue to report it as "current" long after it was discontinued.
3. **Role of the Query Interface:** The project treats the dashboard as a high-level "snapshot" and the query interface as the "canonical answer" for specific clinical questions. For the question "What is she taking right now across her whole history?", the `current_medications` intent provides the more sophisticated, windowed result.

**Result:** The dashboard is a fast, note-based summary. The query interface is the deep-reasoning tool.
