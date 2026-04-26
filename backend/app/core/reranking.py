from dataclasses import replace
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.core.retrieval import RetrievedChunk


RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    """Load the cross-encoder. Cached so we only load once per process."""
    return CrossEncoder(RERANKER_MODEL)


def rerank(
    query: str,
    candidates: list[RetrievedChunk],
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """
    Re-score candidates with a cross-encoder and return the top_k most relevant.

    The cross-encoder produces a relevance score for each (query, chunk) pair
    by encoding them jointly. This catches subtle relationships that pure
    embedding similarity misses — particularly important for queries where the
    answer is buried in a chunk dominated by other content.

    The original `similarity` field on each chunk is preserved (it reflects the
    initial bi-encoder cosine similarity); we add the cross-encoder score
    implicitly by reordering. The chunk's `similarity` is updated to the
    rerank score so the frontend shows reranked relevance.
    """
    if not candidates:
        return []

    if len(candidates) <= top_k:
        return candidates

    model = get_reranker()
    pairs = [(query, c.chunk_text) for c in candidates]
    scores = model.predict(pairs)

    scored = list(zip(candidates, scores))
    scored.sort(key=lambda x: float(x[1]), reverse=True)

    top = scored[:top_k]
    return [replace(chunk, similarity=float(score)) for chunk, score in top]
