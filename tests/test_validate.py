from studyrag.chunking.validate import check_chunk


def count_words(text: str) -> int:
    return len(text.split())


def row(**kw) -> dict:
    base = {"id": "manuals/x#0", "category": "manuals", "source": "x.pdf", "headings": ["Bearings"],
            "pages": [3], "labels": ["text"], "text": "grease " * 30, "embed_text": "grease " * 30,
            "license_note": "ABB copyright"}
    return base | kw


def test_good_chunk_passes():
    assert check_chunk(row(), count_words, 512) == ([], [])


def test_flags_oversized_and_missing_fields():
    assert check_chunk(row(embed_text="a " * 600), count_words, 512)[0] == ["embed_text has 600 tokens > 512"]
    assert check_chunk({"id": "x"}, count_words, 512)[0][0].startswith("missing fields")


def test_flags_pii_only_in_redacted_sources():
    text = "contact 9876543210 " + "motor " * 30
    assert check_chunk(row(text=text), count_words, 512)[0] == []
    assert check_chunk(row(text=text, license_note="redact PII"), count_words, 512)[0] == ["unredacted PII"]


def test_warns_on_ocr_garbage():
    _, warnings = check_chunk(row(text="可可3T，可3T 开TR可HT 府市永府市R页 " * 5), count_words, 512)
    assert any("bad OCR" in w for w in warnings)
