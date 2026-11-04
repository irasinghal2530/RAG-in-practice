import pytest

from studyrag.retrieval import dense


def test_dense_search_returns_k_chunks():
    try:
        results = dense.search("bearing temperature limit", k=3)
    except NotImplementedError:
        pytest.skip("dense.search not built yet")
    assert len(results) == 3
    assert {"chunk_id", "text", "score"} <= results[0].keys()
