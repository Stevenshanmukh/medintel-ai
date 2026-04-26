from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import patients, query
from app.core.embeddings import get_embedding_model
from app.core.reranking import get_reranker
from app.db.session import get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load ML models so the first request isn't slow."""
    print("Loading embedding model...")
    get_embedding_model()
    print("Loading reranker model...")
    get_reranker()
    print("Models ready.")
    yield


app = FastAPI(
    title="MedIntel AI",
    description="Clinical intelligence system",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(patients.router)
app.include_router(query.router)


@app.get("/")
def root():
    return {"service": "medintel-ai", "version": "0.2.0"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        result = db.execute(text("SELECT 1")).scalar()
        db_ok = result == 1
    except Exception as e:
        return {"status": "degraded", "db": "disconnected", "error": str(e)}

    try:
        ext = db.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        pgvector_ok = ext == "vector"
    except Exception:
        pgvector_ok = False

    return {
        "status": "ok" if db_ok and pgvector_ok else "degraded",
        "db": "connected" if db_ok else "disconnected",
        "pgvector": "installed" if pgvector_ok else "missing",
    }
