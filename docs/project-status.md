# MedIntel AI — Current Project Status

## Where we are
Week 6 complete. Patient dashboard, risk detection engine, and visit timeline all fully integrated.

## Stack
- Backend: FastAPI, Python 3.11, SQLAlchemy, pgvector, scispaCy + negspacy, LangChain
- Frontend: Next.js 14, TypeScript, Tailwind, shadcn (radix-based, post-base-ui swap)
- LLM: OpenAI GPT-4o-mini via LangChain
- Embeddings: BAAI/bge-small-en-v1.5 (local CPU)
- Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2 (local CPU, top-50 candidate pool)
- Database: Postgres 16 + pgvector

- Sarah Chen synthetic data: 1 patient, 8 visits, 61 chunks, 123 entities
- Intent-based clinical QA: SQL-backed structured paths (medications, first occurrence, all mentions) + RAG-backed narrative synthesis + safety refusals
- Patient List: Central directory of all patients with visit counts
- Patient Dashboard: Compact clinical summary including risk alerts (severity hierarchy), current medications/concerns, and recent activity (last 3 visits)
- Visit Timeline: Full longitudinal scroll with deep-links from dashboard and interactive trend charting
- Explainability: Unified visual system for disclosing evidence (SQL results or RAG chunks) across all paths

## Documented limitations (in docs/known-issues-and-resolutions.md)
1. Temporal recall failure on "first appearance" queries (partially resolved via structured layer)
2. Incomplete medication synthesis from RAG path (resolved via structured layer)
3. Negation misattribution on interrogative-then-denied (resolved via turn-aware negation)
4. Severity extraction is sparse (regex-based, accepted)
5. Cross-turn negation (resolved, with over-negation caveat on compound questions)
6. scispaCy entity granularity loss (e.g. "tightness" extracted without "chest" qualifier)

- Week 7: Evaluation harness with real numbers (intent accuracy, retrieval metrics, GPT-4-as-judge scoring)
- Week 8: README, deployment, demo script

## Key file locations
- backend/app/core/: ingestion.py, embeddings.py, retrieval.py, reranking.py,
  entities.py, structured_query.py, query_classifier.py, reasoning.py
- backend/app/api/: query.py, patients.py
- backend/app/models/: patient.py, visit.py, visit_chunk.py, visit_entity.py
- frontend/app/query/page.tsx
- docs/known-issues-and-resolutions.md
