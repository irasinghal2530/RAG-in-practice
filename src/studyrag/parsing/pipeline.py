"""Step 1: raw PDFs -> DoclingDocument (saved by the CLI as JSON + Markdown in data/parsed/)."""

from functools import cache
from pathlib import Path

from docling.document_converter import DocumentConverter


@cache
def _converter() -> DocumentConverter:
    # loading the layout/OCR models is slow: build once, reuse for every PDF
    return DocumentConverter()


def parse_pdf(pdf_path: Path):
    return _converter().convert(pdf_path).document
