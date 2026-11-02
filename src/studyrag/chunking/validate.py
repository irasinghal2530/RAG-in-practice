"""
# Sanity checks on data/processed/chunks.jsonl, kept separate from the chunker so it can be
# run on any chunks file after the fact.

# Errors (exit code 1): missing fields, duplicate ids, empty text, embed_text over the token
# budget, PII left in a source that must be redacted.
# Warnings: tiny chunks, chunks with no pages/headings, OCR-garbage text, duplicate text,
# parsed documents that produced no chunks.
"""

import json
import logging
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path

from studyrag.config import CHUNKS_FILE, PARSED_DIR
from studyrag.parsing.pii import PII_PATTERNS, needs_redaction

log = logging.getLogger(__name__)

REQUIRED = ["id", "category", "source", "headings", "pages", "labels", "text", "embed_text"]
MIN_TOKENS = 20
MAX_GARBAGE_RATIO = 0.3  # share of characters that are not ASCII letters/digits/punctuation/space
GARBAGE = re.compile(r"[^\x20-\x7E\n\t°±µΩ–—’“”•×]")


def check_chunk(row: dict, count_tokens: Callable[[str], int], max_tokens: int) -> tuple[list, list]:
    """Return (errors, warnings) for one chunk."""
    errors, warnings = [], []
    missing = [k for k in REQUIRED if k not in row]
    if missing:
        return [f"missing fields {missing}"], []
    text = row["text"].strip()
    if not text:
        return ["empty text"], []

    n = count_tokens(row["embed_text"])
    if n > max_tokens:
        errors.append(f"embed_text has {n} tokens > {max_tokens}")
    elif n < MIN_TOKENS:
        warnings.append(f"only {n} tokens")
    if needs_redaction(row.get("license_note")) and any(p.search(row["text"]) for p, _ in PII_PATTERNS):
        errors.append("unredacted PII")
    if not row["pages"]:
        warnings.append("no page numbers")
    if not row["headings"]:
        warnings.append("no headings")
    garbage = len(GARBAGE.findall(text)) / len(text)
    if garbage > MAX_GARBAGE_RATIO:
        warnings.append(f"{garbage:.0%} non-text characters (bad OCR?)")
    return errors, warnings


def run(tokenizer: str, max_tokens: int, chunks_file: Path = CHUNKS_FILE, show: int = 5) -> int:
    from studyrag.chunking.chunker import load_tokenizer

    tok = load_tokenizer(tokenizer)
    # count like the embedding model sees it: [CLS] text [SEP]
    count_tokens = lambda text: len(tok.encode(text, add_special_tokens=True))
    print(f"Validating {chunks_file} ({tokenizer}, max {max_tokens} tokens)")
    rows = [json.loads(line) for line in chunks_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Loaded {len(rows)} chunks")

    errors, warnings = defaultdict(list), defaultdict(list)  # message kind -> [(chunk id, message)]
    sizes = {}
    for row in rows:
        errs, warns = check_chunk(row, count_tokens, max_tokens)
        for found, msgs in [(errors, errs), (warnings, warns)]:
            for msg in msgs:
                found[re.sub(r"\d+%?", "N", msg)].append((row.get("id"), msg))
        if "embed_text" in row:
            sizes[row.get("id")] = count_tokens(row["embed_text"])

    for id_, n in Counter(r.get("id") for r in rows).items():
        if n > 1:
            errors["duplicate id"].append((id_, f"{n} copies"))
    for text, n in Counter(r.get("text", "").strip() for r in rows).items():
        if n > 1 and text:
            warnings["duplicate text"].append((text[:60], f"{n} copies"))
    chunked = {(r.get("category"), Path(r.get("source", "")).stem) for r in rows}
    for path in sorted(PARSED_DIR.glob("*/*.json")):
        if (path.parent.name, path.stem) not in chunked:
            warnings["parsed document has no chunks"].append((f"{path.parent.name}/{path.stem}", ""))

    per_source = Counter(f"{r.get('category')}/{r.get('source')}" for r in rows)
    log.info("%d chunks from %d sources in %s", len(rows), len(per_source), chunks_file)
    for source, n in sorted(per_source.items()):
        log.info("  %5d  %s", n, source)
    for title, found, level in [("ERROR", errors, logging.ERROR), ("WARN", warnings, logging.WARNING)]:
        for kind, items in found.items():
            log.log(level, "[%s] %s: %d", title, kind, len(items))
            for id_, msg in items[:show]:
                log.log(level, "    %s  %s", id_, msg)

    oversized = sorted(((n, id_) for id_, n in sizes.items() if n > max_tokens), reverse=True)
    print(f"Overflowing chunks (> {max_tokens} tokens): {len(oversized)}")
    for n, id_ in oversized:  # all of them, not just the first `show`
        print(f"    {id_}: {n} tokens")
    largest = max(sizes.values(), default=0)
    print(f"Largest chunk: {largest} tokens (limit {max_tokens})")
    print(f"Errors: {sum(map(len, errors.values()))}, warnings: {sum(map(len, warnings.values()))}")
    print("Validation passed" if not errors else "Validation FAILED")
    return 1 if errors else 0


if __name__ == "__main__":  # running this file directly = `studyrag validate-chunks`
    import sys

    from studyrag.cli import main
    sys.exit(main(["validate-chunks", *sys.argv[1:]]))
