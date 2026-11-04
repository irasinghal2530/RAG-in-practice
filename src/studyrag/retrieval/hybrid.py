"""Hybrid retrieval: fuse dense + sparse results (e.g. reciprocal rank fusion)."""

from studyrag import config


def search(question: str, k: int = config.TOP_K) -> list[dict]:
    """Return the top k chunks after fusing dense.search and sparse.search."""
    raise NotImplementedError
