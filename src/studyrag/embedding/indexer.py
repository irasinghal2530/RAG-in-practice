"""
Embeds data/processed/chunks.jsonl and stores the vectors in a local Qdrant collection.

Each chunk's `embed_text` (headings + text) is embedded with the same model the chunks were
sized for; vectors are L2-normalised, so cosine distance = dot product. The payload keeps every
other chunk field (text, source, pages, url, ...) so a search hit can be shown and cited
without going back to chunks.jsonl. Like the chunker, the collection is rebuilt on every run.
"""

import json
import logging
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from studyrag.config import CHUNKS_FILE, COLLECTION, VECTOR_DB_DIR

log = logging.getLogger(__name__)

# bge models expect this prefix on queries (not on passages)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
UPSERT_BATCH = 256


def point_id(chunk_id: str) -> str:
    """Qdrant ids must be ints or UUIDs; derive a stable UUID from the chunk id."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def load_model(model: str):
    from sentence_transformers import SentenceTransformer  # slow import (torch)
    return SentenceTransformer(model, device="cpu")


def open_store(path: Path = VECTOR_DB_DIR) -> QdrantClient:
    path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(path))


def to_point(row: dict, vector) -> PointStruct:
    payload = {k: v for k, v in row.items() if k != "embed_text"}
    return PointStruct(id=point_id(row["id"]), vector=vector.tolist(), payload=payload)


def run(model: str, chunks_file: Path = CHUNKS_FILE, collection: str = COLLECTION, batch_size: int = 32) -> int:
    rows = [json.loads(line) for line in chunks_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Embedding {len(rows)} chunks from {chunks_file} with {model}")
    encoder = load_model(model)
    vectors = encoder.encode([r["embed_text"] for r in rows], batch_size=batch_size,
                             normalize_embeddings=True, show_progress_bar=True)

    client = open_store()
    if client.collection_exists(collection):
        client.delete_collection(collection)
    client.create_collection(collection, vectors_config=VectorParams(size=vectors.shape[1], distance=Distance.COSINE))
    for start in range(0, len(rows), UPSERT_BATCH):
        batch = zip(rows[start:start + UPSERT_BATCH], vectors[start:start + UPSERT_BATCH])
        client.upsert(collection, points=[to_point(r, v) for r, v in batch])

    stored = client.count(collection).count
    print(f"Stored {stored} vectors ({vectors.shape[1]} dims, cosine) in collection '{collection}' at {VECTOR_DB_DIR}")
    client.close()
    if stored != len(rows):
        log.error("expected %d vectors, found %d", len(rows), stored)
        return 1
    return 0


class DenseRetriever:
    """Loads the encoder and opens the store once, for running many queries (e.g. evals)."""

    def __init__(self, model: str, collection: str = COLLECTION):
        self.encoder = load_model(model)
        self.client = open_store()
        self.collection = collection

    def search(self, query: str, k: int = 5, category: str | None = None) -> list[dict]:
        """Top-k chunks for a query (dense only; hybrid search + reranking is stage 5)."""
        vector = self.encoder.encode(QUERY_PREFIX + query, normalize_embeddings=True, show_progress_bar=False)
        where = Filter(must=[FieldCondition(key="category", match=MatchValue(value=category))]) if category else None
        hits = self.client.query_points(self.collection, query=vector.tolist(), limit=k, query_filter=where).points
        return [{"score": h.score, **h.payload} for h in hits]

    def close(self) -> None:
        self.client.close()


def search(query: str, model: str, k: int = 5, category: str | None = None,
           collection: str = COLLECTION) -> list[dict]:
    retriever = DenseRetriever(model, collection)
    try:
        return retriever.search(query, k, category)
    finally:
        retriever.close()




# """
# Dense indexing and retrieval for StudyRag.

# Indexing:
#     uv run studyrag embed

# Retrieval:
#     Create one DenseRetriever and reuse it for multiple queries.

# Evaluation:
#     Use evaluate_retrieval() with the evaluation JSON file.
# """

# import json
# import logging
# import time
# import uuid
# from pathlib import Path
# from typing import Any

# from qdrant_client import QdrantClient
# from qdrant_client.models import (
#     Distance,
#     FieldCondition,
#     Filter,
#     MatchValue,
#     PointStruct,
#     VectorParams,
# )

# from studyrag.config import CHUNKS_FILE, COLLECTION, VECTOR_DB_DIR

# log = logging.getLogger(__name__)

# QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
# UPSERT_BATCH = 256


# def point_id(chunk_id: str) -> str:
#     """Create a stable Qdrant UUID from a chunk ID."""
#     return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


# def load_model(model: str):
#     """Load the sentence-transformer model."""
#     from sentence_transformers import SentenceTransformer

#     print(f"[MODEL] Loading embedding model: {model}")
#     started = time.perf_counter()
#     encoder = SentenceTransformer(model, device="cpu")
#     print(f"[MODEL] Model loaded in {time.perf_counter() - started:.2f}s")
#     return encoder


# def open_store(path: Path = VECTOR_DB_DIR) -> QdrantClient:
#     """Open a local Qdrant database."""
#     path.mkdir(parents=True, exist_ok=True)
#     print(f"[QDRANT] Opening local database: {path}")
#     return QdrantClient(path=str(path))


# def to_point(row: dict, vector) -> PointStruct:
#     """Convert a chunk and its vector into a Qdrant point."""
#     payload = {key: value for key, value in row.items() if key != "embed_text"}
#     return PointStruct(
#         id=point_id(row["id"]),
#         vector=vector.tolist(),
#         payload=payload,
#     )


# def run(
#     model: str,
#     chunks_file: Path = CHUNKS_FILE,
#     collection: str = COLLECTION,
#     batch_size: int = 32,
# ) -> int:
#     """Embed all chunks and rebuild the local Qdrant collection."""
#     total_started = time.perf_counter()

#     print("\n========== STUDYRAG INDEXING STARTED ==========")
#     print(f"[INPUT] Reading chunks from: {chunks_file}")

#     rows = [
#         json.loads(line)
#         for line in chunks_file.read_text(encoding="utf-8").splitlines()
#         if line.strip()
#     ]

#     if not rows:
#         raise ValueError(f"No chunks found in {chunks_file}")

#     required_fields = {"id", "embed_text"}
#     for index, row in enumerate(rows, start=1):
#         missing = required_fields - row.keys()
#         if missing:
#             raise ValueError(f"Chunk at row {index} is missing fields: {sorted(missing)}")

#     print(f"[INPUT] Loaded {len(rows):,} chunks")
#     print("[INPUT] Example chunk ID:", rows[0]["id"])
#     print("[INPUT] Example text preview:", rows[0]["embed_text"][:200].replace("\n", " "))

#     encoder = load_model(model)

#     print(f"[EMBED] Embedding {len(rows):,} chunks...")
#     embed_started = time.perf_counter()

#     vectors = encoder.encode(
#         [row["embed_text"] for row in rows],
#         batch_size=batch_size,
#         normalize_embeddings=True,
#         show_progress_bar=True,
#     )

#     embed_seconds = time.perf_counter() - embed_started
#     print(f"[EMBED] Finished in {embed_seconds:.2f}s")
#     print(f"[EMBED] Vector matrix shape: {vectors.shape}")

#     client = open_store()
#     try:
#         if client.collection_exists(collection):
#             print(f"[QDRANT] Collection '{collection}' already exists.")
#             print("[QDRANT] Deleting it because this indexer performs a full rebuild.")
#             client.delete_collection(collection)

#         print(f"[QDRANT] Creating collection '{collection}'...")
#         client.create_collection(
#             collection_name=collection,
#             vectors_config=VectorParams(
#                 size=vectors.shape[1],
#                 distance=Distance.COSINE,
#             ),
#         )

#         print(f"[QDRANT] Uploading vectors in batches of {UPSERT_BATCH}...")
#         for start in range(0, len(rows), UPSERT_BATCH):
#             end = min(start + UPSERT_BATCH, len(rows))
#             batch_rows = rows[start:end]
#             batch_vectors = vectors[start:end]

#             points = [
#                 to_point(row, vector)
#                 for row, vector in zip(batch_rows, batch_vectors)
#             ]

#             client.upsert(collection_name=collection, points=points)
#             print(f"[QDRANT] Uploaded chunks {start + 1:,}-{end:,} of {len(rows):,}")

#         stored = client.count(collection_name=collection, exact=True).count
#         print(f"[QDRANT] Stored vectors: {stored:,}")
#         print(f"[QDRANT] Collection: {collection}")
#         print(f"[QDRANT] Database path: {VECTOR_DB_DIR}")

#         if stored != len(rows):
#             log.error("Expected %d vectors, found %d", len(rows), stored)
#             print("[ERROR] Stored vector count does not match input chunk count.")
#             return 1

#     finally:
#         client.close()

#     print(f"[DONE] Indexing completed in {time.perf_counter() - total_started:.2f}s")
#     print("========== STUDYRAG INDEXING FINISHED ==========\n")
#     return 0


# class DenseRetriever:
#     """Keep one model and Qdrant connection open for repeated searches."""

#     def __init__(self, model: str, collection: str = COLLECTION, verbose: bool = True):
#         self.encoder = load_model(model)
#         self.client = open_store()
#         self.collection = collection
#         self.verbose = verbose

#         if not self.client.collection_exists(collection):
#             self.client.close()
#             raise RuntimeError(
#                 f"Qdrant collection '{collection}' does not exist. Run indexing first."
#             )

#         if self.verbose:
#             count = self.client.count(collection_name=collection, exact=True).count
#             print(f"[RETRIEVER] Ready. Collection '{collection}' contains {count:,} points.")

#     def search(
#         self,
#         query: str,
#         k: int = 5,
#         category: str | None = None,
#     ) -> list[dict[str, Any]]:
#         """Embed only the query, then retrieve the top-k stored document vectors."""
#         started = time.perf_counter()

#         if self.verbose:
#             print("\n[SEARCH] Query:", query)
#             print(f"[SEARCH] Requested top-k: {k}")
#             if category:
#                 print(f"[SEARCH] Category filter: {category}")

#         query_vector = self.encoder.encode(
#             QUERY_PREFIX + query,
#             normalize_embeddings=True,
#             show_progress_bar=False,
#         )

#         if self.verbose:
#             print(f"[SEARCH] Query vector dimensions: {len(query_vector)}")

#         where = (
#             Filter(
#                 must=[
#                     FieldCondition(
#                         key="category",
#                         match=MatchValue(value=category),
#                     )
#                 ]
#             )
#             if category
#             else None
#         )

#         hits = self.client.query_points(
#             collection_name=self.collection,
#             query=query_vector.tolist(),
#             limit=k,
#             query_filter=where,
#         ).points

#         results = [{"score": hit.score, **(hit.payload or {})} for hit in hits]

#         if self.verbose:
#             print(f"[SEARCH] Retrieved {len(results)} chunks in {time.perf_counter() - started:.3f}s")
#             for rank, result in enumerate(results, start=1):
#                 print(
#                     f"\n  Rank {rank} | score={result.get('score', 0):.4f}"
#                     f" | source={result.get('source', 'N/A')}"
#                     f" | pages={result.get('pages', 'N/A')}"
#                 )
#                 preview = str(result.get("text", "")).replace("\n", " ")
#                 print("  Text:", preview[:350])

#         return results

#     def close(self) -> None:
#         self.client.close()
#         if self.verbose:
#             print("[RETRIEVER] Qdrant connection closed.")


# def search(
#     query: str,
#     model: str,
#     k: int = 5,
#     category: str | None = None,
#     collection: str = COLLECTION,
# ) -> list[dict]:
#     """Convenience function for a single query. Reuse DenseRetriever for many queries."""
#     retriever = DenseRetriever(model, collection)
#     try:
#         return retriever.search(query, k, category)
#     finally:
#         retriever.close()


# def evaluate_retrieval(
#     retriever: DenseRetriever,
#     evaluation_file: Path,
#     output_file: Path = Path("data/evaluation/retrieval_results.json"),
#     k: int = 5,
# ) -> dict:
#     """
#     Evaluate retrieval against manually verified questions.

#     evidence: expected source ID; compared with each retrieved chunk's `source`.
#     contains: phrase expected inside a retrieved chunk's `text`.

#     This evaluates retrieval evidence, not whether an LLM-generated answer is correct.
#     """
#     dataset = json.loads(evaluation_file.read_text(encoding="utf-8"))
#     if not isinstance(dataset, list):
#         raise ValueError("Evaluation JSON must contain a list of question objects.")

#     print("\n========== RETRIEVAL EVALUATION STARTED ==========")
#     print(f"[EVAL] Questions: {len(dataset)}")
#     print(f"[EVAL] Retrieving top-{k} chunks per question")

#     per_question = []
#     source_hits = 0
#     evidence_hits = 0
#     reciprocal_ranks = []

#     for item in dataset:
#         question_id = item["id"]
#         question = item["question"]
#         expected_source = item["evidence"]
#         expected_phrase = item.get("contains", "")
#         category = item.get("category")

#         print(f"\n[EVAL] {question_id}: {question}")
#         hits = retriever.search(question, k=k, category=category)

#         source_rank = None
#         evidence_rank = None

#         for rank, hit in enumerate(hits, start=1):
#             same_source = str(hit.get("source", "")) == str(expected_source)
#             text = str(hit.get("text", ""))
#             phrase_found = (
#                 not expected_phrase
#                 or expected_phrase.casefold() in text.casefold()
#             )

#             if same_source and source_rank is None:
#                 source_rank = rank

#             if same_source and phrase_found and evidence_rank is None:
#                 evidence_rank = rank

#         source_found = source_rank is not None
#         evidence_found = evidence_rank is not None

#         source_hits += int(source_found)
#         evidence_hits += int(evidence_found)

#         if evidence_rank is not None:
#             reciprocal_ranks.append(1.0 / evidence_rank)
#         else:
#             reciprocal_ranks.append(0.0)

#         status = "PASS" if evidence_found else "FAIL"
#         print(f"[EVAL] Expected source: {expected_source}")
#         print(f"[EVAL] Source found in top-{k}: {source_found}")
#         print(f"[EVAL] Expected phrase found in expected source: {evidence_found}")
#         print(f"[EVAL] Result: {status}")

#         per_question.append(
#             {
#                 "id": question_id,
#                 "type": item.get("type"),
#                 "category": category,
#                 "question": question,
#                 "expected_source": expected_source,
#                 "expected_contains": expected_phrase,
#                 "expected_answer": item.get("answer"),
#                 "source_found_at_rank": source_rank,
#                 "evidence_found_at_rank": evidence_rank,
#                 "source_hit_at_k": source_found,
#                 "evidence_hit_at_k": evidence_found,
#                 "retrieved": [
#                     {
#                         "rank": rank,
#                         "score": hit.get("score"),
#                         "source": hit.get("source"),
#                         "pages": hit.get("pages"),
#                         "text": hit.get("text"),
#                     }
#                     for rank, hit in enumerate(hits, start=1)
#                 ],
#             }
#         )

#     total = len(dataset)
#     metrics = {
#         "total_questions": total,
#         "k": k,
#         "source_recall_at_k": source_hits / total if total else 0.0,
#         "evidence_recall_at_k": evidence_hits / total if total else 0.0,
#         "evidence_mrr_at_k": (
#             sum(reciprocal_ranks) / total if total else 0.0
#         ),
#     }

#     report = {
#         "metrics": metrics,
#         "results": per_question,
#     }

#     output_file.parent.mkdir(parents=True, exist_ok=True)
#     output_file.write_text(
#         json.dumps(report, indent=2, ensure_ascii=False),
#         encoding="utf-8",
#     )

#     print("\n========== EVALUATION SUMMARY ==========")
#     print(f"Questions evaluated: {total}")
#     print(f"Source Recall@{k}: {metrics['source_recall_at_k']:.3f}")
#     print(f"Evidence Recall@{k}: {metrics['evidence_recall_at_k']:.3f}")
#     print(f"Evidence MRR@{k}: {metrics['evidence_mrr_at_k']:.3f}")
#     print(f"[EVAL] Detailed report saved to: {output_file}")
#     print("========== RETRIEVAL EVALUATION FINISHED ==========\n")

#     return report
