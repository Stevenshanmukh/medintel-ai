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

**Partial resolution (this week):** Cross-encoder reranking with candidate
pool of 50, top-5 returned. Verified to improve general retrieval quality on
non-temporal queries.

**Full resolution (in progress):** Clinical entity extraction (scispaCy)
produces structured `(symptom, visit_date, severity)` rows at ingestion time.
"First appearance" queries can then be answered by SQL: `SELECT MIN(visit_date)
FROM visit_entities WHERE entity_text ILIKE '%chest%' AND negated = false`.
This converts a hard retrieval problem into a trivial database query, which is
the correct architecture for fact-list and temporal questions.

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
