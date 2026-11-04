import pytest

from studyrag import config
from studyrag.parsing.pipeline import parse_pdf


@pytest.mark.slow
def test_parse_pdf_returns_text():
    pdfs = sorted(config.RAW_DIR.rglob("*.pdf"), key=lambda p: p.stat().st_size)
    if not pdfs:
        pytest.skip("no PDFs in data/raw")
    doc = parse_pdf(pdfs[0])
    assert doc.export_to_markdown().strip()
