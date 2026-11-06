"""
studyrag - command line entry point.

    studyrag parse                          parse every PDF in data/raw
    studyrag parse --only manuals           only the data/raw/manuals folder
    studyrag parse --only abb_lv_motors     only that file (name without .pdf)
    studyrag parse --force                  re-parse files that were already parsed
    studyrag -v parse                       same, with DEBUG messages (-v goes before "parse")

Input and output folders come from config.py (RAW_DIR, PARSED_DIR).
The actual PDF -> document conversion lives in parsing/pipeline.py (parse_pdf).
Each run appends a record to logs/runs.jsonl and logs to logs/studyrag.log (see runlog.py).
"""

import argparse
import logging
import sys
import time

from studyrag import config, runlog

log = logging.getLogger("studyrag")

# saved in each runs.jsonl record so you know which parser produced the output
DOCLING_MODEL = {"parser": "docling DocumentConverter (see parsing/pipeline.py for options)"}
# PARSER_INFO = {
#     "parser": "Docling DocumentConverter"
# }

def cmd_parse(only: list[str] | None, force: bool) -> None:
    """data/raw/<category>/x.pdf -> data/parsed/<category>/x.json + x.md"""
    # runlog.stage times the whole parse and appends one record to logs/runs.jsonl at the end,
    # with the counts / items collected through `s` (see runlog.py)
    with runlog.stage("parse", model=DOCLING_MODEL, only=only, force=force) as s:
        # imported here, not at the top: docling loads torch, which is slow
        from studyrag.parsing.pipeline import parse_pdf

        # 1. find the PDFs, optionally limited by --only (folder name or file name)
        pdfs = sorted(config.RAW_DIR.rglob("*.pdf"))
        if only:
            pdfs = [p for p in pdfs if p.relative_to(config.RAW_DIR).parts[0] in only or p.stem in only]
        s.count("documents_found", len(pdfs))
        log.info("parsing %d PDFs from %s", len(pdfs), config.RAW_DIR)

        # 2. parse each one and save it, keeping the same folder layout as data/raw
        for i, pdf in enumerate(pdfs, 1):
            out = config.PARSED_DIR / pdf.relative_to(config.RAW_DIR).with_suffix(".json")
            if out.exists() and not force:
                log.info("[%d/%d] skip %s (already parsed, use --force)", i, len(pdfs), pdf.name)
                s.count("skipped")
                continue

            log.info("[%d/%d] parse %s", i, len(pdfs), pdf.name)
            t0 = time.perf_counter()
            try:
                doc = parse_pdf(pdf)
            except Exception:
                log.exception("failed to parse %s", pdf)  # keep going with the next PDF
                s.count("failed")
                s.item(doc=pdf.stem, status="failed", seconds=round(time.perf_counter() - t0, 2))
                continue

            out.parent.mkdir(parents=True, exist_ok=True)
            doc.save_as_json(out)
            out.with_suffix(".md").write_text(doc.export_to_markdown(), encoding="utf-8")
            s.count("parsed")
            s.count("pages", doc.num_pages())
            s.item(doc=pdf.stem, status="parsed", pages=doc.num_pages(),
                   seconds=round(time.perf_counter() - t0, 2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="studyrag")
    ap.add_argument("-v", "--verbose", action="store_true", help="show DEBUG messages too")
    sub = ap.add_subparsers(dest="command", required=True)

    parse = sub.add_parser("parse", help="convert raw PDFs to Docling JSON + Markdown")
    parse.add_argument("--only", nargs="*", help="category folders (manuals, ...) or file names without .pdf")
    parse.add_argument("--force", action="store_true", help="re-parse files that are already parsed")

    args = ap.parse_args(argv)
    # the Windows console defaults to cp1252, which can't print characters like "≤" or "mm²"
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    # console + logs/studyrag.log, DEBUG level with -v
    runlog.setup_logging(args.verbose)

    if args.command == "parse":
        cmd_parse(args.only, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
