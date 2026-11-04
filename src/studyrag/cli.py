"""
studyrag - command line entry point for the pipeline.

    studyrag ingest [--only manuals]                      download sources -> data/raw (not built yet)
    studyrag parse  [--only manuals standards] [--force]  data/raw/**/*.pdf -> data/parsed (Docling JSON + Markdown)
    studyrag chunk  [--only manuals]                      data/parsed/**/*.json -> data/processed/chunks.jsonl
    studyrag embed                                        chunks.jsonl -> vector DB
    studyrag run    [--only manuals] [--force] [--embed]  parse + chunk (+ embed) in one go
    studyrag search "query" [-k 5] [--mode dense]         top-k chunks
    studyrag eval   [-k 5] [--mode dense]                 hit/recall/mrr@k -> evals/runs/<mode>_k<k>_<time>.json
    studyrag runs   [-n 20] [--failed]                    recent stage records from logs/runs.jsonl
    studyrag search "What is the maximum ambient temperature for the motor?" -k 5 --mode dense
--only takes category folders (manuals, standards, ...) and/or file names without extension
(abb_lv_motors_iom_2009), so you can run one category, a few files, or everything.

Every stage appends a record to logs/runs.jsonl (see runlog.py); console output also goes to
logs/studyrag.log.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from studyrag import config, runlog

log = logging.getLogger("studyrag")

DOCLING_MODEL = {"parser": "docling DocumentConverter (default PDF pipeline: layout + tables + OCR)"}
CHUNKER_MODEL = {"chunker": "docling HybridChunker", "tokenizer": config.EMBED_MODEL,
                 "max_tokens": config.CHUNK_SIZE - 2}
EMBED_MODEL = {"embedding": config.EMBED_MODEL, "vector_db": "qdrant (local)",
               "collection": config.COLLECTION}
SEARCH_MODELS = {"dense": EMBED_MODEL, "sparse": {"retriever": "bm25"},
                 "hybrid": {**EMBED_MODEL, "retriever": "dense + bm25 fusion"}}


def _files(root: Path, pattern: str, only: list[str] | None) -> list[Path]:
    """Files under root matching pattern, limited to `only` (category folders or file stems)."""
    files = sorted(p for p in root.rglob(pattern) if p.name != "manifest.json")
    if only:
        files = [f for f in files if f.relative_to(root).parts[0] in only or f.stem in only]
    return files


def cmd_ingest(only: list[str] | None) -> None:
    with runlog.stage("ingest", only=only):
        from studyrag.ingestion.scraper import download_all
        download_all(only)


def cmd_parse(only: list[str] | None, force: bool) -> None:
    with runlog.stage("parse", model=DOCLING_MODEL, only=only, force=force) as s:
        from studyrag.parsing.pipeline import parse_pdf

        pdfs = _files(config.RAW_DIR, "*.pdf", only)
        s.count("documents_found", len(pdfs))
        log.info("parsing %d PDFs from %s", len(pdfs), config.RAW_DIR)
        failed = []
        for i, pdf in enumerate(pdfs, 1):
            # mirror the raw layout: data/raw/manuals/x.pdf -> data/parsed/manuals/x.json + x.md
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
                log.exception("failed to parse %s", pdf)
                failed.append(pdf.name)
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
        if failed:
            log.warning("%d PDFs failed to parse: %s", len(failed), ", ".join(failed))


def cmd_chunk(only: list[str] | None) -> None:
    with runlog.stage("chunk", model=CHUNKER_MODEL, only=only) as s:
        from docling_core.types.doc import DoclingDocument

        from studyrag.chunking.pipeline import chunk_document

        docs = _files(config.PARSED_DIR, "*.json", only)
        s.count("documents_found", len(docs))
        if not docs:
            log.warning("no parsed documents in %s, run `studyrag parse` first", config.PARSED_DIR)
            return
        log.info("chunking %d parsed documents from %s", len(docs), config.PARSED_DIR)
        config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        s.details["output"] = str(config.CHUNKS_FILE)
        total = 0
        with open(config.CHUNKS_FILE, "w", encoding="utf-8") as f:
            for i, path in enumerate(docs, 1):
                doc_id = path.stem
                category = path.relative_to(config.PARSED_DIR).parts[0]
                t0 = time.perf_counter()
                chunks = chunk_document(DoclingDocument.load_from_json(path))
                for n, chunk in enumerate(chunks):
                    record = {"chunk_id": f"{doc_id}:{n}", "doc_id": doc_id, "category": category, **chunk}
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total += len(chunks)
                s.count("documents")
                s.count("chunks", len(chunks))
                s.item(doc=doc_id, chunks=len(chunks), seconds=round(time.perf_counter() - t0, 2))
                if not chunks:
                    log.warning("%s produced no chunks", doc_id)
                log.info("[%d/%d] %s: %d chunks", i, len(docs), doc_id, len(chunks))
        log.info("wrote %d chunks to %s", total, config.CHUNKS_FILE)


def cmd_embed() -> None:
    with runlog.stage("embed", model=EMBED_MODEL) as s:
        from studyrag.embeddings.pipeline import build_index

        with open(config.CHUNKS_FILE, encoding="utf-8") as f:
            s.count("chunks", sum(1 for line in f if line.strip()))
        s.details["input"] = str(config.CHUNKS_FILE)
        s.details["output"] = str(config.VECTOR_DB_DIR)
        build_index()


def _search_fn(mode: str):
    if mode == "dense":
        from studyrag.retrieval.dense import search
    elif mode == "sparse":
        from studyrag.retrieval.sparse import search
    else:
        from studyrag.retrieval.hybrid import search
    return search


def cmd_search(query: str, k: int, mode: str) -> None:
    with runlog.stage("retrieval", model=SEARCH_MODELS[mode], query=query, k=k, mode=mode) as s:
        hits = _search_fn(mode)(query, k)
        s.count("results", len(hits))
        s.details["results"] = [{"rank": r, "chunk_id": h["chunk_id"], "score": round(h["score"], 4)}
                                for r, h in enumerate(hits, 1)]
    for r in hits:
        print(f"{r['score']:.3f}  {r['chunk_id']}\n    {r['text'][:200]!r}")


def cmd_eval(k: int, mode: str) -> None:
    with runlog.stage("eval", model=SEARCH_MODELS[mode], k=k, mode=mode,
                      questions_file=str(config.QUESTIONS_FILE)) as s:
        from studyrag.evaluation.evaluate import evaluate

        summary, path = evaluate(_search_fn(mode), k, mode)
        for key in ("questions_loaded", "questions_scored", "questions_skipped", "questions_unanswerable"):
            s.count(key, summary[key])
        s.details["metrics"] = summary["overall"]
        s.details["output"] = str(path)
    o = summary["overall"]
    print(f"{mode} k={k}  n={o['n']}  hit@k={o['hit']:.3f}  "
          f"recall@k={o['recall']:.3f}  mrr={o['mrr']:.3f}")
    print(f"human validation file: {path}")


def cmd_runs(n: int, failed_only: bool) -> None:
    records = runlog.recent(n * 10 if failed_only else n)
    if failed_only:
        records = [r for r in records if r["status"] != "success"][-n:]
    for r in records:
        counts = " ".join(f"{k}={v}" for k, v in r["counts"].items())
        print(f"{r['started_at'][:19]}  {r['run_id']}  {r['operation']:<9} {r['status']:<11} "
              f"{r['seconds']:>8.1f}s  w={len(r['warnings'])} e={len(r['errors'])}  {counts}")
        if r.get("exception"):
            print(f"    {r['exception']['type']}: {r['exception']['message']}")
    print(f"\nfull records: {runlog.RUNS_FILE}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="studyrag")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="command", required=True)
    only_help = "only these categories (manuals, standards, ...) or file names without extension"

    ingest = sub.add_parser("ingest", help="download sources into data/raw")
    ingest.add_argument("--only", nargs="*", help=only_help)

    parse = sub.add_parser("parse", help="convert raw PDFs to Docling JSON + Markdown")
    parse.add_argument("--only", nargs="*", help=only_help)
    parse.add_argument("--force", action="store_true", help="re-parse files that are already parsed")

    chunk = sub.add_parser("chunk", help="build data/processed/chunks.jsonl from parsed documents")
    chunk.add_argument("--only", nargs="*", help=only_help)

    sub.add_parser("embed", help="embed chunks.jsonl into the vector DB")

    run = sub.add_parser("run", help="parse + chunk (+ embed) in one go")
    run.add_argument("--only", nargs="*", help=only_help)
    run.add_argument("--force", action="store_true", help="re-parse files that are already parsed")
    run.add_argument("--embed", action="store_true", help="also embed the chunks")

    search = sub.add_parser("search", help="print the top-k chunks for a query")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=config.TOP_K)
    search.add_argument("--mode", choices=["dense", "sparse", "hybrid"], default="dense")

    evaluate = sub.add_parser("eval", help="retrieval recall@k on the golden questions")
    evaluate.add_argument("-k", type=int, default=config.TOP_K)
    evaluate.add_argument("--mode", choices=["dense", "sparse", "hybrid"], default="dense")

    runs = sub.add_parser("runs", help="show recent stage records from logs/runs.jsonl")
    runs.add_argument("-n", type=int, default=20)
    runs.add_argument("--failed", action="store_true", help="only partial / failed / interrupted stages")

    args = ap.parse_args(argv)
    # the Windows console defaults to cp1252, which can't print chunk text like "≤" or "mm²"
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    runlog.setup_logging(args.verbose)

    # imports are lazy inside each command: docling pulls in torch, which is slow to load
    if args.command == "ingest":
        cmd_ingest(args.only)
    elif args.command == "parse":
        cmd_parse(args.only, args.force)
    elif args.command == "chunk":
        cmd_chunk(args.only)
    elif args.command == "embed":
        cmd_embed()
    elif args.command == "run":
        cmd_parse(args.only, args.force)
        cmd_chunk(args.only)
        if args.embed:
            cmd_embed()
    elif args.command == "search":
        cmd_search(args.query, args.k, args.mode)
    elif args.command == "eval":
        cmd_eval(args.k, args.mode)
    elif args.command == "runs":
        cmd_runs(args.n, args.failed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
