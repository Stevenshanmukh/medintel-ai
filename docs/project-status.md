# MedIntel AI — Current Project Status

## Where we are
Week 3 complete. Hybrid RAG + structured query system fully functional.

## Stack
- Backend: FastAPI, Python 3.11, SQLAlchemy, pgvector, scispaCy + negspacy, LangChain
- Frontend: Next.js 14, TypeScript, Tailwind, shadcn (radix-based, post-base-ui swap)
- LLM: OpenAI GPT-4o-mini via LangChain
- Embeddings: BAAI/bge-small-en-v1.5 (local CPU)
- Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2 (local CPU, top-50 candidate pool)
- Database: Postgres 16 + pgvector

## What's working end-to-end
- Sarah Chen synthetic data: 1 patient, 8 visits, 61 chunks, 123 entities
- Five query paths via intent classifier:
  1. current_medications → SQL with drug-name validation against COMMON_MEDICATIONS list
  2. first_occurrence → SQL with smart subject keyword extraction (_subject_to_pattern)
  3. all_mentions → SQL with affirmed/negated split
  4. narrative_synthesis → RAG with cross-encoder reranking
  5. unanswerable_or_unsafe → safety refusal, no patient data accessed
- Frontend renders three distinct visual modes by path

## Documented limitations (in docs/known-issues-and-resolutions.md)
1. Temporal recall failure on "first appearance" queries (partially resolved via structured layer)
2. Incomplete medication synthesis from RAG path (resolved via structured layer)
3. Negation misattribution on interrogative-then-denied (resolved via turn-aware negation)
4. Severity extraction is sparse (regex-based, accepted)
5. Cross-turn negation (resolved, with over-negation caveat on compound questions)
6. scispaCy entity granularity loss (e.g. "tightness" extracted without "chest" qualifier)

## What's next: Full plan, weeks 4-8
- Week 4: Longitudinal reasoning + visit timeline frontend page
- Week 5: Risk detection engine
- Week 6: Patient dashboard + explainability panel
- Week 7: Evaluation harness with real numbers
- Week 8: README, deployment, demo

## Key file locations
- backend/app/core/: ingestion.py, embeddings.py, retrieval.py, reranking.py,
  entities.py, structured_query.py, query_classifier.py, reasoning.py
- backend/app/api/: query.py, patients.py
- backend/app/models/: patient.py, visit.py, visit_chunk.py, visit_entity.py
- frontend/app/query/page.tsx
- docs/known-issues-and-resolutions.md
