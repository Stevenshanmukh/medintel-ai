from functools import lru_cache

from sentence_transformers import SentenceTransformer


MODEL_NAME = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Load the embedding model. Cached so we only load once per process."""
    return SentenceTransformer(MODEL_NAME)


def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns a list of 384 floats."""
    model = get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in a batch. Much faster than calling embed_text in a loop."""
    model = get_embedding_model()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [emb.tolist() for emb in embeddings]
