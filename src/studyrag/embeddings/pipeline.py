"""Step 3: chunks.jsonl -> embeddings -> vector DB (config.VECTOR_DB_DIR, local Qdrant)."""

import json
import logging
import shutil

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from studyrag import config

log = logging.getLogger(__name__)


def load_chunks() -> list[dict]:
    with open(config.CHUNKS_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_index() -> None:
    """Embed every chunk with config.EMBED_MODEL and store it in config.COLLECTION.

    Rebuilds the vector DB from scratch, so it always matches chunks.jsonl.
    """
    chunks = load_chunks()
    log.info("embedding %d chunks with %s", len(chunks), config.EMBED_MODEL)

    model = SentenceTransformer(config.EMBED_MODEL)
    # embed_text = chunk text with its section headings prepended (chunker.contextualize)
    vectors = model.encode(
        [c["embed_text"] for c in chunks],
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    # wipe the folder instead of delete_collection: on Windows local Qdrant leaves the old
    # storage.sqlite behind and reloads its points into the "new" collection
    shutil.rmtree(config.VECTOR_DB_DIR, ignore_errors=True)
    client = QdrantClient(path=str(config.VECTOR_DB_DIR))
    client.create_collection(
        config.COLLECTION,
        vectors_config=VectorParams(size=vectors.shape[1], distance=Distance.COSINE),
    )
    # Qdrant ids must be ints or UUIDs, so the row number is the id; chunk_id goes in the payload
    client.upsert(
        config.COLLECTION,
        points=[
            PointStruct(id=i, vector=v.tolist(), payload=c)
            for i, (c, v) in enumerate(zip(chunks, vectors))
        ],
    )
    client.close()
    log.info("indexed %d chunks into %s/%s", len(chunks), config.VECTOR_DB_DIR, config.COLLECTION)
