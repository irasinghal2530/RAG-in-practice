"""Dense retrieval: embed the question, nearest neighbours in the vector DB."""

import atexit
from functools import cache

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from studyrag import config

# BGE v1.5 is trained with this prefix on queries (not on passages)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@cache
def _model() -> SentenceTransformer:
    return SentenceTransformer(config.EMBED_MODEL)


@cache
def _client() -> QdrantClient:
    # local Qdrant locks its folder: one client per process, reused across searches
    client = QdrantClient(path=str(config.VECTOR_DB_DIR))
    # close before interpreter teardown, else __del__ raises "sys.meta_path is None" at exit
    atexit.register(client.close)
    return client


def search(question: str, k: int = config.TOP_K) -> list[dict]:
    """Return the k most similar chunks, each with its chunk_id, text and score."""
    vector = _model().encode(QUERY_PREFIX + question, normalize_embeddings=True)
    hits = _client().query_points(config.COLLECTION, query=vector.tolist(), limit=k).points
    return [
        {"chunk_id": h.payload["chunk_id"], "doc_id": h.payload["doc_id"],
         "pages": h.payload.get("pages"), "text": h.payload["text"], "score": h.score}
        for h in hits
    ]
