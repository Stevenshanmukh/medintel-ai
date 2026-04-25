# MedIntel AI

An open-source clinical intelligence system that transforms doctor-patient conversation transcripts into structured clinical knowledge, enabling longitudinal analysis and grounded reasoning via a hybrid RAG architecture.

**Status:** Active development.

## Tech Stack

- **Backend:** FastAPI, Python 3.11, SQLAlchemy 2.0
- **Database:** PostgreSQL 16 with pgvector
- **LLM:** OpenAI GPT-4o-mini via LangChain
- **Embeddings:** sentence-transformers (BGE-small-en-v1.5), local CPU inference
- **Frontend:** Next.js 14, TypeScript, Tailwind CSS
- **Orchestration:** Docker Compose

## Quick Start

```bash
git clone https://github.com/Stevenshanmukh/medintel-ai.git
cd medintel-ai
cp .env.example .env
docker compose up --build
```

Then visit:
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Roadmap

- [x] Week 1: Foundation (FastAPI + Postgres+pgvector + Next.js skeleton)
- [ ] Week 2: Text-only RAG pipeline
- [ ] Week 3: Clinical NLP and structured retrieval
- [ ] Weeks 4-6: Longitudinal reasoning, risk detection, explainability
- [ ] Week 7: Evaluation harness
- [ ] Week 8: Polish and deployment