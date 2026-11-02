"""
Paths and settings shared by every pipeline stage.

Everything can be overridden with environment variables (or a .env loaded by your shell),
so the same code runs locally, in CI and in a container with a mounted data volume.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("STUDYRAG_DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"              # untouched downloads + source manifest
PARSED_DIR = DATA_DIR / "parsed"        # DoclingDocument JSON + Markdown per source
PROCESSED_DIR = DATA_DIR / "processed"  # chunks ready for embedding

SOURCE_MANIFEST = RAW_DIR / "manifest.json"
PARSE_MANIFEST = PARSED_DIR / "manifest.json"
CHUNKS_FILE = PROCESSED_DIR / "chunks.jsonl"

# chunks are sized for the tokenizer of the embedding model that will index them
EMBED_TOKENIZER = os.environ.get("STUDYRAG_EMBED_TOKENIZER", "BAAI/bge-small-en-v1.5")
CHUNK_MAX_TOKENS = int(os.environ.get("STUDYRAG_CHUNK_MAX_TOKENS", "512"))

# embedding model + vector store (Qdrant in embedded mode: a folder on disk, no server)
EMBED_MODEL = os.environ.get("STUDYRAG_EMBED_MODEL", EMBED_TOKENIZER)
VECTOR_DB_DIR = Path(os.environ.get("STUDYRAG_VECTOR_DB_DIR", DATA_DIR / "vectordb"))
COLLECTION = os.environ.get("STUDYRAG_COLLECTION", "chunks")

# golden questions live in the repo (not under data/) so they are versioned with the code
EVALS_DIR = PROJECT_ROOT / "evals"
QUESTIONS_FILE = EVALS_DIR / "questions.jsonl"
RUNS_DIR = EVALS_DIR / "runs"
