from studyrag.parsing.pii import needs_redaction, redact


def test_redacts_indian_identifiers():
    text = "PAN: ABCDE1234F, IFSC SBIN0001234, A/c No. 1234 5678 9012, call 9876543210"
    out = redact(text)
    assert "ABCDE1234F" not in out and "[PAN]" in out
    assert "SBIN0001234" not in out and "[IFSC]" in out
    assert "1234 5678 9012" not in out and "[BANK ACCOUNT]" in out
    assert "9876543210" not in out and "[PHONE]" in out


def test_leaves_technical_text_alone():
    text = "Motor 15 kW, 415 V, 1460 rpm, IE3 per IS 12615:2011, code 3AXD50000016097"
    assert redact(text) == text


def test_redaction_is_driven_by_source_note():
    assert needs_redaction("BEE (Govt of India) public report - redact PII (PAN, bank details) at ingestion")
    assert not needs_redaction("ABB copyright - use locally, do not redistribute")
    assert not needs_redaction(None)
