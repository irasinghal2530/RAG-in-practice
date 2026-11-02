"""
Splits the parsed DoclingDocuments into token-bounded RAG chunks in data/processed/chunks.jsonl.

Docling's HybridChunker follows the document structure (sections, tables, lists), then
splits/merges to fit the embedding model's token budget; table headers are repeated when
a table is split. Each chunk keeps its heading path, page numbers and source/licence info.
The file is always rebuilt from every parsed document, so it never goes stale.
"""

import json
import logging
from pathlib import Path

from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc import DoclingDocument
from transformers import AutoTokenizer, PreTrainedTokenizerBase

from studyrag.config import CHUNKS_FILE, PARSED_DIR, RAW_DIR, SOURCE_MANIFEST
from studyrag.parsing.pii import needs_redaction, redact
from studyrag.utils import read_json

log = logging.getLogger(__name__)


def load_source_info() -> dict:
    """filename -> {url, note} from the download manifest (its paths are OS-specific)."""
    return {Path(e["file"].replace("\\", "/")).name: e for e in read_json(SOURCE_MANIFEST, [])}


def load_tokenizer(tokenizer: str) -> PreTrainedTokenizerBase:
    tok = AutoTokenizer.from_pretrained(tokenizer)
    # HybridChunker measures whole sections (10k+ tokens) before splitting them; lift the
    # model's 512 limit on the tokenizer so that measuring doesn't log a bogus overflow warning
    tok.model_max_length = int(1e9)
    return tok


def build_chunker(tokenizer: str, max_tokens: int) -> HybridChunker:
    tok = load_tokenizer(tokenizer)
    # Docling counts tokens without the [CLS]/[SEP] the model adds when embedding, so leave room for them
    budget = max_tokens - tok.num_special_tokens_to_add()
    return HybridChunker(tokenizer=HuggingFaceTokenizer(tokenizer=tok, max_tokens=budget),
                         merge_peers=True, repeat_table_header=True)


def chunk_document(doc: DoclingDocument, chunker: HybridChunker, category: str,
                   source: Path, src_info: dict) -> list[dict]:
    redacting = needs_redaction(src_info.get("note"))
    rows = []
    for i, chunk in enumerate(chunker.chunk(dl_doc=doc)):
        pages = sorted({p.page_no for item in chunk.meta.doc_items for p in item.prov})
        text, embed_text = chunk.text, chunker.contextualize(chunk=chunk)
        if redacting:
            text, embed_text = redact(text), redact(embed_text)
        rows.append({
            "id": f"{category}/{source.stem}#{i}",
            "category": category,
            "source": source.name,
            "title": doc.name,
            "headings": chunk.meta.headings or [],
            "pages": pages,
            "labels": sorted({str(item.label) for item in chunk.meta.doc_items}),
            "text": text,                # raw chunk text, for showing to the user / LLM
            "embed_text": embed_text,    # headings prepended, for the embedding model
            "url": src_info.get("url"),
            "license_note": src_info.get("note"),
        })
    return rows


def run(tokenizer: str, max_tokens: int) -> int:
    chunker = build_chunker(tokenizer, max_tokens)
    info = load_source_info()
    CHUNKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with CHUNKS_FILE.open("w", encoding="utf-8") as f:
        for json_path in sorted(PARSED_DIR.glob("*/*.json")):
            category = json_path.parent.name
            source = RAW_DIR / category / f"{json_path.stem}.pdf"
            doc = DoclingDocument.load_from_json(json_path)
            rows = chunk_document(doc, chunker, category, source, info.get(source.name, {}))
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            total += len(rows)
            log.info("%s/%s: %d chunks", category, json_path.stem, len(rows))
    log.info("Chunks: %s (%d chunks, <= %d tokens for %s)", CHUNKS_FILE, total, max_tokens, tokenizer)
    return 0
