"""Step 2: parsed text -> data/processed/chunks.jsonl.

One JSON object per line: {"chunk_id", "doc_id", "category", "pages", "text", "embed_text"}.
Keep chunk_id stable (e.g. f"{doc_id}:{n}"): your eval questions point at it.
"""

from functools import cache

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer

from studyrag import config


@cache
def _chunker() -> HybridChunker:
    # tokenizer must match the embedding model, so chunk sizes are counted in its tokens
    tokenizer = HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(config.EMBED_MODEL),
        # the chunker counts tokens without [CLS]/[SEP]; the embedder adds them, so leave room
        max_tokens=config.CHUNK_SIZE - 2,
    )
    return HybridChunker(tokenizer=tokenizer)


def chunk_document(doc) -> list[dict]:
    chunker = _chunker()
    chunks = []
    for chunk in chunker.chunk(dl_doc=doc):
        pages = sorted({p.page_no for item in chunk.meta.doc_items for p in item.prov})
        chunks.append({
            "pages": pages,
            "text": chunk.text,
            # headings prepended: this is what gets embedded
            "embed_text": chunker.contextualize(chunk=chunk),
        })
    return chunks
