"""Paths and settings shared by every step. Plain constants: change them here."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"              # PDFs, CSVs (input)
PARSED_DIR = DATA_DIR / "parsed"        # parse.py output: clean text per document
PROCESSED_DIR = DATA_DIR / "processed"  # chunk.py output
CHUNKS_FILE = PROCESSED_DIR / "chunks.jsonl"
VECTOR_DB_DIR = DATA_DIR / "vectordb"   # index.py output (Qdrant, local folder)

CHUNK_SIZE = 512        # tokens
CHUNK_OVERLAP = 64
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
COLLECTION = "chunks"
TOP_K = 5

EVALS_DIR = PROJECT_ROOT / "evals"
QUESTIONS_FILE = EVALS_DIR / "questions.jsonl"
