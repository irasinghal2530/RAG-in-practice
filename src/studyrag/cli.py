"""
studyrag - command line entry point for the data pipeline.

    studyrag ingest [--only manuals drives] [--skip-cwru-48k]   download sources -> data/raw
    studyrag parse  [--only standards] [--force]                 PDFs -> data/parsed (Docling)
    studyrag chunk  [--tokenizer ...] [--max-tokens 512]         parsed -> data/processed/chunks.jsonl
    studyrag validate-chunks [--max-tokens 512] [--show 5]     sanity-check chunks.jsonl
    studyrag embed  [--model ...] [--batch-size 32]              chunks.jsonl -> Qdrant (data/vectordb)
    studyrag search "query" [-k 5] [--category manuals]         dense search over the stored chunks
    studyrag eval [-k 10] [--tag dense-baseline]                 retrieval metrics on evals/questions.jsonl
    studyrag eval-check                                          validate questions against chunks.jsonl
    studyrag eval-compare BASE NEW                               metric deltas between two saved runs
"""

import argparse
import logging
import sys
from pathlib import Path

from studyrag import config


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="studyrag")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="download all sources into data/raw")
    ingest.add_argument("--only", nargs="*", help="download only these categories")
    ingest.add_argument("--skip-cwru-48k", action="store_true",
                        help="skip the 48 kHz CWRU files (the largest part of the download)")

    parse = sub.add_parser("parse", help="convert raw PDFs to DoclingDocuments with Docling")
    parse.add_argument("--only", nargs="*", help="parse only these categories")
    parse.add_argument("--force", action="store_true", help="re-parse files even if unchanged")
    parse.add_argument("--threads", type=int, default=None)

    chunk = sub.add_parser("chunk", help="build data/processed/chunks.jsonl from parsed documents")
    chunk.add_argument("--tokenizer", default=config.EMBED_TOKENIZER,
                       help="HF tokenizer of the embedding model the chunks are sized for")
    chunk.add_argument("--max-tokens", type=int, default=config.CHUNK_MAX_TOKENS)

    validate = sub.add_parser("validate-chunks", help="sanity-check data/processed/chunks.jsonl")
    validate.add_argument("--tokenizer", default=config.EMBED_TOKENIZER)
    validate.add_argument("--max-tokens", type=int, default=config.CHUNK_MAX_TOKENS)
    validate.add_argument("--show", type=int, default=5, help="example chunk ids to print per issue")

    embed = sub.add_parser("embed", help="embed chunks.jsonl into the Qdrant collection")
    embed.add_argument("--model", default=config.EMBED_MODEL)
    embed.add_argument("--batch-size", type=int, default=32)

    search = sub.add_parser("search", help="search the stored chunks")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=5)
    search.add_argument("--category", help="only search this category (manuals, standards, ...)")
    search.add_argument("--model", default=config.EMBED_MODEL)

    evaluate = sub.add_parser("eval", help="retrieval metrics on the golden questions")
    evaluate.add_argument("-k", type=int, default=10)
    evaluate.add_argument("--tag", help="save the run as evals/runs/<tag>.json")
    evaluate.add_argument("--questions", type=Path, default=config.QUESTIONS_FILE)
    evaluate.add_argument("--model", default=config.EMBED_MODEL)

    eval_check = sub.add_parser("eval-check", help="validate the golden questions against chunks.jsonl")
    eval_check.add_argument("--questions", type=Path, default=config.QUESTIONS_FILE)

    eval_compare = sub.add_parser("eval-compare", help="compare two saved eval runs")
    eval_compare.add_argument("base", help="tag or path of the baseline run")
    eval_compare.add_argument("new", help="tag or path of the new run")

    args = ap.parse_args(argv)
    # the Windows console defaults to cp1252, which can't print chunk text like "≤" or "mm²"
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    # imported lazily: docling pulls in torch, which is slow to load for `ingest`
    if args.command == "ingest":
        from studyrag.ingestion import downloader
        return downloader.run(args.only, args.skip_cwru_48k)
    if args.command == "parse":
        from studyrag.parsing import pipeline
        return pipeline.run(args.only, args.force, args.threads)
    if args.command == "validate-chunks":
        from studyrag.chunking import validate
        return validate.run(args.tokenizer, args.max_tokens, show=args.show)
    if args.command == "embed":
        from studyrag.embedding import indexer
        return indexer.run(args.model, batch_size=args.batch_size)
    if args.command == "search":
        from studyrag.embedding import indexer
        for hit in indexer.search(args.query, args.model, args.k, args.category):
            print(f"{hit['score']:.3f}  {hit['id']}  pages {hit['pages']}  {' > '.join(hit['headings'])}")
            print("       " + hit["text"][:200].replace("\n", " "))
        return 0
    if args.command == "eval":
        from studyrag.evals import retrieval
        return retrieval.run(args.model, args.k, args.tag, args.questions)
    if args.command == "eval-check":
        from studyrag.evals import retrieval
        return retrieval.check(args.questions)
    if args.command == "eval-compare":
        from studyrag.evals import retrieval
        return retrieval.compare(args.base, args.new)
    from studyrag.chunking import chunker
    return chunker.run(args.tokenizer, args.max_tokens)


if __name__ == "__main__":
    sys.exit(main())
