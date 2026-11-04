"""Sparse retrieval: BM25 keyword search over chunks.jsonl."""

from studyrag import config


def search(question: str, k: int = config.TOP_K) -> list[dict]:
    """Return the k best keyword-matching chunks, each with its chunk_id, text and score."""
    raise NotImplementedError
