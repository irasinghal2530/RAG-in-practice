# StudyRag

Retrieval-augmented copilot for induction motors and drives (Indian manufacturing focus),
built from OEM manuals, BIS standards, DOE/BEE guides, papers and sensor datasets.

## Layout

```
StudyRag/
├── src/studyrag/
│   ├── config.py            paths + settings (env-overridable)
│   ├── cli.py               `studyrag` command
│   ├── ingestion/           stage 1: sources.py (catalog), downloader.py
│   ├── parsing/             stage 2: Docling converter, parse pipeline, PII redaction
│   ├── chunking/            stage 3: HybridChunker -> chunks.jsonl
│   ├── embedding/           stage 4: indexer.py, chunks -> Qdrant (embedded mode)
│   ├── retrieval/           stage 5 (planned)
│   └── generation/          stage 6 (planned)
├── data/                    git-ignored except data/raw/manifest.json
│   ├── raw/<category>/      untouched downloads
│   ├── parsed/<category>/   DoclingDocument .json + .md per PDF, manifest.json
│   ├── processed/           chunks.jsonl
│   └── vectordb/            Qdrant collection (local, no server)
└── tests/
```

## Pipeline

```bash
uv sync
uv run studyrag ingest                 # download sources -> data/raw (+ manifest)
uv run studyrag parse                  # PDFs -> data/parsed (incremental, sha256-keyed)
uv run studyrag chunk                  # -> data/processed/chunks.jsonl
uv run studyrag validate-chunks        # sanity-check the chunks
uv run studyrag embed                  # -> data/vectordb (Qdrant collection `chunks`)
uv run studyrag search "regreasing interval" -k 5 --category manuals
uv run studyrag eval-check                    # validate evals/questions.jsonl against the chunks
uv run studyrag eval -k 10 --tag dense-baseline   # retrieval metrics -> evals/runs/<tag>.json
uv run studyrag eval-compare dense-baseline hybrid
uv run pytest
```

`parse` and `ingest` take `--only <category ...>`; `parse --force` re-parses unchanged files.
Settings come from environment variables (see `.env.example`; `uv run --env-file .env ...`).

### Parsing (Docling)

- TableFormer ACCURATE mode, so troubleshooting and fault-code tables keep their structure.
- Heading hierarchy reconstruction, so every chunk carries its section path.
- `standards/` (scanned BIS codes with a bad text layer) is fully re-OCRed with RapidOCR on
  ONNX Runtime; other PDFs use their native text and OCR only images.

### Chunks

Each line of `chunks.jsonl` has `id`, `category`, `source`, `headings`, `pages`, `labels`,
`text` (to show the LLM), `embed_text` (headings prepended, to embed), `url` and
`license_note`. Chunks are sized for `STUDYRAG_EMBED_TOKENIZER` /
`STUDYRAG_CHUNK_MAX_TOKENS`. Sources whose licence note says "redact PII" have PAN, IFSC,
bank account and phone numbers masked.

### Embeddings and vector store

`embed` encodes each chunk's `embed_text` with `STUDYRAG_EMBED_MODEL` (default
`BAAI/bge-small-en-v1.5`, 384 dims, normalised, cosine) and stores it in a Qdrant collection
running in embedded mode under `data/vectordb`, so no server is needed. Every other chunk
field is stored as the payload, so hits can be shown and cited directly. The collection is
rebuilt on every run (about 7 minutes on CPU for ~1,700 chunks). Only one process can open
the embedded store at a time.

### Retrieval evals

`evals/questions.jsonl` is the golden set, one question per line:

```json
{"id": "q019", "type": "numeric_spec", "category": "standards",
 "question": "By how much can the supply voltage and frequency vary ... under IS 325?",
 "evidence": [{"source": "is_325_1996_three_phase_induction_motors", "pages": [10], "contains": "rated output with"}],
 "answer": "Voltage within +/-6% of rated, frequency within +/-3%, or any combination."}
```

Evidence names the source (file stem), the PDF page(s) and an optional short string the
passage must contain, not chunk ids, so labels survive re-chunking. A retrieved chunk is
relevant if source, pages and string all match. `type` is one of `numeric_spec`,
`table_lookup`, `procedure`, `definition`, `vendor_specific`, `cross_source`, `colloquial`,
`unanswerable` (empty evidence). `answer` is the reference answer for the generation eval.

`eval` reports hit@k, recall@k, MRR and nDCG@k overall and per type/category, lists the
questions whose evidence was missed, and compares the top-1 similarity of answerable and
unanswerable questions. Questions whose sources aren't chunked yet (drives, guides, papers,
WEG manuals) are skipped until those categories are parsed. Run `eval-check` after adding
questions or re-chunking: it fails on any evidence that no chunk matches.
