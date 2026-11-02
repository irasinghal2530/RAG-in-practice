import uuid

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, VectorParams

from studyrag.embedding.indexer import point_id, to_point


def row(id_: str, category: str) -> dict:
    return {"id": id_, "category": category, "source": "x.pdf", "headings": ["Bearings"], "pages": [3],
            "labels": ["text"], "text": "grease the bearings", "embed_text": "Bearings\ngrease the bearings"}


def test_point_id_is_a_stable_uuid():
    assert point_id("manuals/x#0") == point_id("manuals/x#0") != point_id("manuals/x#1")
    uuid.UUID(point_id("manuals/x#0"))


def test_payload_keeps_metadata_but_not_embed_text():
    payload = to_point(row("manuals/x#0", "manuals"), np.ones(4)).payload
    assert "embed_text" not in payload and payload["text"] == "grease the bearings"


def test_roundtrip_with_category_filter():
    client = QdrantClient(":memory:")
    client.create_collection("t", vectors_config=VectorParams(size=2, distance=Distance.COSINE))
    client.upsert("t", points=[to_point(row("manuals/x#0", "manuals"), np.array([1.0, 0.0])),
                               to_point(row("standards/y#0", "standards"), np.array([0.9, 0.1]))])
    hits = client.query_points("t", query=[1.0, 0.0], limit=2).points
    assert [h.payload["id"] for h in hits] == ["manuals/x#0", "standards/y#0"]
    only = Filter(must=[FieldCondition(key="category", match=MatchValue(value="standards"))])
    hits = client.query_points("t", query=[1.0, 0.0], limit=2, query_filter=only).points
    assert [h.payload["id"] for h in hits] == ["standards/y#0"]
