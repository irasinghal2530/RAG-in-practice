"""Redaction of Indian PII that BEE audit reports can contain (PAN, IFSC, bank accounts, phones)."""

import re

PII_PATTERNS = [
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN]"),
    (re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"), "[IFSC]"),
    (re.compile(r"(?i)\b(a/?c|account)(\s*(no\.?|number))?\s*[:.\-]?\s*\d[\d -]{7,20}\d"), "[BANK ACCOUNT]"),
    (re.compile(r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b"), "[PHONE]"),
]


def needs_redaction(source_note: str | None) -> bool:
    """The scraper's licence note flags sources that must be redacted at ingestion."""
    return "redact pii" in (source_note or "").lower()


def redact(text: str) -> str:
    for pattern, repl in PII_PATTERNS:
        text = pattern.sub(repl, text)
    return text
