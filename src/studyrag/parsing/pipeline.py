"""
Parses every PDF in data/raw/<category>/ with Docling into data/parsed/<category>/:
    <name>.json   lossless DoclingDocument (layout, tables, reading order, page provenance)
    <name>.md     human-readable Markdown export

data/parsed/manifest.json records the source sha256 of every parsed file, so reruns
only touch new or changed PDFs.
"""

import logging
import time
from datetime import datetime, timezone

from studyrag.config import PARSE_MANIFEST, PARSED_DIR, RAW_DIR
from studyrag.parsing.converter import build_converter
from studyrag.utils import read_json, sha256, write_json

log = logging.getLogger(__name__)

# categories whose PDFs are scans with a poor embedded OCR layer -> re-OCR every page
# (the BIS standards from law.resource.org read "bavingoutput", ":tJO%")
FORCE_OCR_CATEGORIES = {"standards"}


def pdf_categories() -> list[str]:
    return sorted(p.name for p in RAW_DIR.iterdir() if p.is_dir() and any(p.glob("*.pdf")))


def run(only: list | None = None, force: bool = False, threads: int | None = None) -> int:
    wanted = set(only) if only else set(pdf_categories())
    manifest = read_json(PARSE_MANIFEST, {})
    converters = {}  # force_ocr -> converter, built lazily since model loading is slow
    failures = []

    for category in pdf_categories():
        if category not in wanted:
            continue
        log.info("== %s ==", category)
        out_dir = PARSED_DIR / category
        out_dir.mkdir(parents=True, exist_ok=True)
        force_ocr = category in FORCE_OCR_CATEGORIES
        for pdf in sorted((RAW_DIR / category).glob("*.pdf")):
            key = f"{category}/{pdf.name}"
            digest = sha256(pdf)
            json_out = out_dir / f"{pdf.stem}.json"
            if not force and manifest.get(key, {}).get("sha256") == digest and json_out.exists():
                log.info("[skip] %s: unchanged", pdf.name)
                continue
            if force_ocr not in converters:
                converters[force_ocr] = build_converter(force_ocr, threads)
            t0 = time.time()
            try:
                result = converters[force_ocr].convert(pdf, raises_on_error=False)
                doc = result.document
                doc.save_as_json(json_out)
                doc.save_as_markdown(out_dir / f"{pdf.stem}.md")
            except Exception as e:  # noqa: BLE001
                failures.append((key, str(e)))
                log.error("[FAIL] %s: %s", pdf.name, e)
                continue
            errors = [str(err.error_message) for err in result.errors]
            manifest[key] = {
                "sha256": digest, "status": str(result.status.value),
                "pages": len(doc.pages), "tables": len(doc.tables), "force_ocr": force_ocr,
                "errors": errors, "seconds": round(time.time() - t0, 1),
                "parsed_at": datetime.now(timezone.utc).isoformat(),
            }
            write_json(PARSE_MANIFEST, manifest)  # save progress per file
            log.info("[%s] %s: %d pages, %d tables, %.0fs", "ok" if not errors else "partial",
                     pdf.name, len(doc.pages), len(doc.tables), time.time() - t0)
            for err in errors[:3]:
                log.warning("    %s", err)

    if failures:
        log.error("%d failed:", len(failures))
        for key, err in failures:
            log.error("  %s: %s", key, err)
    return 1 if failures else 0
