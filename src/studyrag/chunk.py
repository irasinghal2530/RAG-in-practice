"""Step 2: parsed text -> data/processed/chunks.jsonl.

One JSON object per line: {"chunk_id", "doc_id", "page", "text"}.
Keep chunk_id stable (e.g. f"{doc_id}:{n}"): your eval questions point at it.
"""

from studyrag import config
from transformers import AutoTokenizer

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import (
    HuggingFaceTokenizer
)

def chunk_document(doc):

    # Load tokenizer matching the embedding model
    tokenizer = AutoTokenizer.from_pretrained(
        "BAAI/bge-small-en-v1.5"
    )

    docling_tokenizer = HuggingFaceTokenizer(
        tokenizer=tokenizer,
        max_tokens=512
    )

    # Initialize HybridChunker
    chunker = HybridChunker(
        tokenizer=docling_tokenizer
    )

    chunks = []

    for chunk in chunker.chunk(dl_doc=doc):

        chunks.append({
            "text": chunk.text,
            "embed_text": chunker.contextualize(chunk=chunk)
        })

    return chunks