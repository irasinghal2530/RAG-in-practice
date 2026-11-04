"""Retrieval eval: for each question in config.QUESTIONS_FILE, did search() find the right chunk?

A chunk is relevant to an evidence item when it comes from that source (doc_id) and its text
contains the evidence's "contains" string (case and whitespace insensitive). Pages are reported
for the human reviewer but not used for matching.

Every run writes evals/runs/<mode>_k<k>_<timestamp>.json: the metrics plus, per question, the
retrieved chunks with blank human_verdict / review_notes fields to fill in by hand.
"""

import json
import logging
import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from studyrag import config

log = logging.getLogger(__name__)

RUNS_DIR = config.EVALS_DIR / "runs"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def load_questions() -> list[dict]:
    """Questions from the JSONL file; lines that aren't a JSON object (// comments, ###) are skipped."""
    with open(config.QUESTIONS_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip().startswith("{")]


def load_chunks() -> list[dict]:
    with open(config.CHUNKS_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _matches(chunk: dict, evidence: dict) -> bool:
    return chunk["doc_id"] == evidence["source"] and _norm(evidence["contains"]) in _norm(chunk["text"])


def _score_question(q: dict, hits: list[dict], chunks: list[dict]) -> dict:
    evidence = q["evidence"]
    # which retrieved ranks satisfy each evidence item
    found_at = [[r for r, h in enumerate(hits, 1) if _matches(h, ev)] for ev in evidence]
    # chunks anywhere in the corpus that satisfy each evidence item (the gold chunks)
    gold = [[c["chunk_id"] for c in chunks if _matches(c, ev)] for ev in evidence]
    ranks = sorted({r for rs in found_at for r in rs})
    first = ranks[0] if ranks else None
    metrics = {
        "hit": float(bool(ranks)),
        "recall": sum(bool(rs) for rs in found_at) / len(evidence),
        "mrr": 1 / first if first else 0.0,
        "first_relevant_rank": first,
        "evidence_found_at": ranks,
    }
    if ranks:
        status = "evidence_found"
    elif not any(gold):
        # the "contains" text is in no chunk at all: a parsing/chunking (or question) problem
        status = "evidence_not_in_any_chunk"
    else:
        status = "evidence_not_found_in_top_k"
    return {"metrics": metrics, "status": status, "gold": gold}


def _mean(rows: list[dict], key: str) -> float:
    return round(sum(r["retrieval_metrics"][key] for r in rows) / len(rows), 4) if rows else 0.0


def _summary(rows: list[dict]) -> dict:
    return {"n": len(rows), **{m: _mean(rows, m) for m in ("hit", "recall", "mrr")}}


def evaluate(search: Callable[[str, int], list[dict]], k: int = config.TOP_K,
             mode: str = "dense") -> tuple[dict, Path]:
    """Run every question through search(), score it, and write the human-validation JSON."""
    start = time.perf_counter()
    questions = load_questions()
    chunks = load_chunks()
    indexed = {c["doc_id"] for c in chunks}

    records, scored = [], []
    for q in questions:
        record = {
            "id": q["id"], "type": q.get("type"), "category": q.get("category"),
            "question": q["question"],
            "expected_answer": q.get("answer"),
            "expected_evidence": q["evidence"],
        }
        missing = sorted({ev["source"] for ev in q["evidence"]} - indexed)
        if not q["evidence"]:
            # unanswerable: nothing to score, but keep the hits so the reviewer sees what came back
            record["status"] = "unanswerable"
        elif missing:
            record |= {"status": "skipped_source_not_indexed", "missing_sources": missing}
            records.append(record | {"human_verdict": "PENDING", "review_notes": ""})
            continue

        hits = search(q["question"], k)
        if q["evidence"]:
            result = _score_question(q, hits, chunks)
            record |= {"retrieval_metrics": result["metrics"], "status": result["status"],
                       "gold_chunk_ids": result["gold"]}
            scored.append(record)
        record["retrieved_chunks"] = [
            {"rank": r, "chunk_id": h["chunk_id"], "score": round(h["score"], 6),
             "source": h["doc_id"], "pages": h.get("pages"), "text": h["text"],
             "matches_evidence": [i for i, ev in enumerate(q["evidence"]) if _matches(h, ev)]}
            for r, h in enumerate(hits, 1)
        ]
        records.append(record | {"human_verdict": "PENDING", "review_notes": ""})

    by_type: dict[str, list[dict]] = {}
    for r in scored:
        by_type.setdefault(r["type"], []).append(r)
    summary = {
        "overall": _summary(scored),
        "by_type": {t: _summary(rs) for t, rs in sorted(by_type.items())},
        "questions_loaded": len(questions),
        "questions_scored": len(scored),
        "questions_skipped": sum(r["status"] == "skipped_source_not_indexed" for r in records),
        "questions_unanswerable": sum(r["status"] == "unanswerable" for r in records),
    }

    out = {
        "purpose": "Human validation of expected answers against retrieved chunks",
        "instructions": "For each question, compare expected_answer with retrieved_chunks[].text. "
                        "Check whether the retrieved text supports the answer, not merely whether "
                        "the source/page matches. Fill human_verdict with PASS, FAIL, or PARTIAL "
                        "and add review_notes.",
        "mode": mode, "k": k, "model": config.EMBED_MODEL,
        "chunk_size": config.CHUNK_SIZE, "chunks_indexed": len(chunks),
        "questions_file": str(config.QUESTIONS_FILE),
        "seconds": round(time.perf_counter() - start, 2),
        "summary": summary,
        "questions": records,
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{mode}_k{k}_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("wrote %s", path)
    return summary, path
