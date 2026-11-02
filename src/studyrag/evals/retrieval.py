# """
# Retrieval eval: does the retriever put the evidence for each golden question in its top k?

# Questions (evals/questions.jsonl) are labelled with evidence, not chunk ids: the source document,
# the page(s) the answer is on and optionally a short string the passage must contain. Chunk ids
# change whenever the chunker or its token budget changes; evidence labels survive that, so the
# same question set can compare chunking strategies, embedding models and retrievers.

# A retrieved chunk is relevant to an evidence item when it comes from that source, its pages
# overlap the evidence pages and its text contains the string (case- and whitespace-insensitive).

# Metrics, overall and per question type and category:
#   hit@k     share of questions with at least one relevant chunk in the top k
#   recall@k  share of a question's evidence items found in the top k
#   mrr       mean of 1 / rank of the first relevant chunk (0 if none in the top k)
#   ndcg@k    binary-gain nDCG, each evidence item credited once

# Questions whose evidence comes from sources that aren't in chunks.jsonl yet (e.g. drives,
# guides) are skipped and counted, so they start counting once those categories are parsed.
# Unanswerable questions (no evidence) get no retrieval score; their top-1 similarity is reported
# next to that of the answerable ones, as a first look at a "not in the sources" threshold.
# """

# import json
# import math
# import re
# import time
# from collections import defaultdict
# from pathlib import Path
# from statistics import mean
# from typing import Callable

# from studyrag.config import CHUNKS_FILE, QUESTIONS_FILE, RUNS_DIR
# from studyrag.utils import read_json, write_json

# QUESTION_TYPES = {"numeric_spec", "table_lookup", "procedure", "definition", "vendor_specific",
#                   "cross_source", "colloquial", "unanswerable"}
# METRICS = ("hit", "recall", "mrr", "ndcg")

# Retrieve = Callable[[str, int], list[dict]]


# def load_questions(path: Path = QUESTIONS_FILE) -> list[dict]:
#     """One JSON object per line; blank lines and lines starting with // are skipped."""
#     questions = []
#     for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
#         if not line.strip() or line.lstrip().startswith("//"):
#             continue
#         try:
#             questions.append(json.loads(line))
#         except json.JSONDecodeError as e:
#             raise ValueError(f"{path}:{number}: not a complete JSON object ({e.msg}); "
#                              "each question must be on a single line") from None
#     return questions


# def indexed_sources(chunks_file: Path = CHUNKS_FILE) -> set[str]:
#     with chunks_file.open(encoding="utf-8") as f:
#         return {source_of(json.loads(line)) for line in f if line.strip()}


# def source_of(chunk: dict) -> str:
#     return chunk.get("title") or Path(chunk["source"]).stem


# def norm(text: str) -> str:
#     return re.sub(r"\s+", " ", text).strip().lower()


# def matches(chunk: dict, evidence: dict) -> bool:
#     if source_of(chunk) != evidence["source"]:
#         return False
#     if evidence.get("pages") and not set(chunk.get("pages") or []) & set(evidence["pages"]):
#         return False
#     return not evidence.get("contains") or norm(evidence["contains"]) in norm(chunk.get("text", ""))


# def score(evidence: list[dict], hits: list[dict], k: int) -> dict:
#     """Metrics for one question from its ranked hits."""
#     found_at = [None] * len(evidence)  # rank at which each evidence item was first retrieved
#     first_relevant, dcg = None, 0.0
#     for rank, hit in enumerate(hits[:k], start=1):
#         covered = [i for i, ev in enumerate(evidence) if matches(hit, ev)]
#         if not covered:
#             continue
#         first_relevant = first_relevant or rank
#         new = [i for i in covered if found_at[i] is None]
#         for i in new:
#             found_at[i] = rank
#         if new:
#             dcg += 1 / math.log2(rank + 1)
#     ideal = sum(1 / math.log2(r + 1) for r in range(1, min(len(evidence), k) + 1))
#     return {"hit": float(first_relevant is not None),
#             "recall": sum(r is not None for r in found_at) / len(evidence),
#             "mrr": 1 / first_relevant if first_relevant else 0.0,
#             "ndcg": dcg / ideal,
#             "first_relevant_rank": first_relevant,
#             "evidence_found_at": found_at}


# def aggregate(rows: list[dict]) -> dict:
#     return {"n": len(rows), **{m: round(mean(r[m] for r in rows), 4) for m in METRICS}} if rows else {"n": 0}


# def evaluate(questions: list[dict], retrieve: Retrieve, k: int, indexed: set[str]) -> dict:
#     scored, skipped, unanswerable = [], [], []
#     for q in questions:
#         evidence = q.get("evidence") or []
#         if evidence and not all(ev["source"] in indexed for ev in evidence):
#             skipped.append(q["id"])
#             continue
#         hits = retrieve(q["question"], k)
#         top = [{"id": h["id"], "score": round(h["score"], 4), "pages": h.get("pages")} for h in hits]
#         if not evidence:
#             unanswerable.append({"id": q["id"], "top1_score": top[0]["score"] if top else None, "top": top[:3]})
#             continue
#         scored.append({"id": q["id"], "type": q["type"], "category": q["category"],
#                        "question": q["question"], **score(evidence, hits, k), "top": top})

#     by = defaultdict(lambda: defaultdict(list))
#     for row in scored:
#         by["type"][row["type"]].append(row)
#         by["category"][row["category"]].append(row)
#     answerable_top1 = [r["top"][0]["score"] for r in scored if r["top"]]
#     unanswerable_top1 = [u["top1_score"] for u in unanswerable if u["top1_score"] is not None]
#     return {
#         "k": k,
#         "overall": aggregate(scored),
#         "by_type": {t: aggregate(rows) for t, rows in sorted(by["type"].items())},
#         "by_category": {c: aggregate(rows) for c, rows in sorted(by["category"].items())},
#         "top1_score": {"answerable_mean": round(mean(answerable_top1), 4) if answerable_top1 else None,
#                        "unanswerable_mean": round(mean(unanswerable_top1), 4) if unanswerable_top1 else None,
#                        "unanswerable_max": max(unanswerable_top1, default=None)},
#         "skipped_not_indexed": skipped,
#         "questions": scored,
#         "unanswerable": unanswerable,
#     }


# def print_report(report: dict, show_misses: bool = True) -> None:
#     k = report["k"]
#     header = f"{'slice':<28}{'n':>4}  {'hit@' + str(k):>7}{'recall@' + str(k):>10}{'mrr':>7}{'ndcg@' + str(k):>9}"
#     print(header)
#     print("-" * len(header))

#     def line(name: str, agg: dict) -> None:
#         if agg["n"]:
#             print(f"{name:<28}{agg['n']:>4}  {agg['hit']:>7.3f}{agg['recall']:>10.3f}{agg['mrr']:>7.3f}{agg['ndcg']:>9.3f}")

#     line("overall", report["overall"])
#     for group in ("by_type", "by_category"):
#         for name, agg in report[group].items():
#             line(f"  {group[3:]}={name}", agg)
#     t = report["top1_score"]
#     print(f"\ntop-1 similarity: answerable mean {t['answerable_mean']}, "
#           f"unanswerable mean {t['unanswerable_mean']} (max {t['unanswerable_max']})")
#     print(f"skipped (source not indexed yet): {len(report['skipped_not_indexed'])}")
#     if show_misses:
#         misses = [q for q in report["questions"] if q["recall"] < 1]
#         if misses:
#             print(f"\nmissed evidence ({len(misses)}):")
#         for q in misses:
#             print(f"  {q['id']} recall {q['recall']:.2f}  {q['question'][:70]}")
#             print(f"       got: {', '.join(h['id'] for h in q['top'][:3])}")


# def run(model: str, k: int = 10, tag: str | None = None, questions_file: Path = QUESTIONS_FILE) -> int:
#     from studyrag.embedding.indexer import DenseRetriever  # slow import (torch)

#     questions = load_questions(questions_file)
#     retriever = DenseRetriever(model, verbose=False)
#     started = time.perf_counter()
#     try:
#         report = evaluate(questions, lambda q, n: retriever.search(q, n), k, indexed_sources())
#     finally:
#         retriever.close()
#     report |= {"tag": tag, "model": model, "retriever": "dense", "questions_file": str(questions_file),
#                "seconds": round(time.perf_counter() - started, 1)}
#     print_report(report)
#     if tag:
#         out = RUNS_DIR / f"{tag}.json"
#         write_json(out, report)
#         print(f"\nwrote {out}")
#     return 0


# def compare(base: str, new: str) -> int:
#     """Per-slice metric deltas between two saved runs (by tag or path)."""
#     a, b = (read_json(Path(t) if t.endswith(".json") else RUNS_DIR / f"{t}.json", None) for t in (base, new))
#     if a is None or b is None:
#         print(f"run not found: {base if a is None else new}")
#         return 1
#     print(f"{'slice':<28}{'n':>4}" + "".join(f"{m:>16}" for m in METRICS))
#     slices = [("overall", a["overall"], b["overall"])] + [
#         (f"  {g[3:]}={name}", a[g].get(name, {"n": 0}), b[g].get(name, {"n": 0}))
#         for g in ("by_type", "by_category") for name in sorted(set(a[g]) | set(b[g]))]
#     for name, x, y in slices:
#         if not (x["n"] and y["n"]):
#             continue
#         cells = "".join(f"{x[m]:>7.3f}->{y[m]:.3f}" + ("+" if y[m] > x[m] else "-" if y[m] < x[m] else " ")
#                         for m in METRICS)
#         print(f"{name:<28}{y['n']:>4}{cells}")
#     a_q, b_q = ({q["id"]: q for q in r["questions"]} for r in (a, b))
#     for label, ids in (("now found", [i for i in b_q if i in a_q and b_q[i]["hit"] > a_q[i]["hit"]]),
#                        ("now missed", [i for i in b_q if i in a_q and b_q[i]["hit"] < a_q[i]["hit"]])):
#         if ids:
#             print(f"\n{label}: {', '.join(ids)}")
#     return 0


# def check(questions_file: Path = QUESTIONS_FILE, chunks_file: Path = CHUNKS_FILE) -> int:
#     """Validate the question file and that every indexed evidence item matches at least one chunk."""
#     questions = load_questions(questions_file)
#     chunks = [json.loads(line) for line in chunks_file.read_text(encoding="utf-8").splitlines() if line.strip()]
#     indexed = {source_of(c) for c in chunks}
#     errors, ids, pending = [], set(), 0
#     for q in questions:
#         qid = q.get("id", "?")
#         missing = {"id", "question", "type", "category"} - set(q)
#         if missing:
#             errors.append(f"{qid}: missing fields {sorted(missing)}")
#         if qid in ids:
#             errors.append(f"{qid}: duplicate id")
#         ids.add(qid)
#         if q.get("type") not in QUESTION_TYPES:
#             errors.append(f"{qid}: unknown type {q.get('type')!r}")
#         if (q.get("type") == "unanswerable") != (not q.get("evidence")):
#             errors.append(f"{qid}: only unanswerable questions may have no evidence")
#         for ev in q.get("evidence") or []:
#             if ev["source"] not in indexed:
#                 pending += 1
#             elif not any(matches(c, ev) for c in chunks):
#                 errors.append(f"{qid}: no chunk matches {ev}")
#     print(f"{len(questions)} questions, {pending} evidence items in sources not indexed yet")
#     for e in errors:
#         print("  " + e)
#     print("OK" if not errors else f"{len(errors)} problem(s)")
#     return 1 if errors else 0


"""
Dense retrieval evaluation with human-review output.

Input: JSONL (one complete JSON object per line).
Output:
  - <tag>.json: retrieval metrics and compact per-question results
  - <tag>_human_validation.json: expected answers + full retrieved chunk text
"""

import json
import math
import re
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Callable

from studyrag.config import CHUNKS_FILE, QUESTIONS_FILE, RUNS_DIR
from studyrag.utils import read_json, write_json

QUESTION_TYPES = {
    "numeric_spec", "table_lookup", "procedure", "definition",
    "vendor_specific", "cross_source", "colloquial", "unanswerable",
}
METRICS = ("hit", "recall", "mrr", "ndcg")
Retrieve = Callable[[str, int], list[dict]]


def log(message: str) -> None:
    print(f"[EVAL] {message}", flush=True)


def load_questions(path: Path = QUESTIONS_FILE) -> list[dict]:
    """Load JSONL. Also accepts a JSON array for convenience."""
    if not path.exists():
        raise FileNotFoundError(f"Questions file not found: {path}")

    raw = path.read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError(f"Questions file is empty: {path}")

    # Accept a JSON array, but the recommended format is JSONL.
    if raw.startswith("["):
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("The JSON root must be an array.")
        questions = data
    else:
        questions = []
        for line_no, line in enumerate(raw.splitlines(), start=1):
            if not line.strip() or line.lstrip().startswith("//"):
                continue
            try:
                questions.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_no}: invalid JSONL line ({exc.msg}). "
                    "Each question must be one complete JSON object on one line."
                ) from exc

    if not questions:
        raise ValueError(f"No questions found in {path}")
    log(f"Loaded {len(questions)} questions from {path}")
    return questions


def source_aliases(record: dict) -> set[str]:
    """Build comparable source names from common chunk payload fields."""
    aliases = set()
    for key in ("source", "source_id", "document_id", "title", "filename"):
        value = record.get(key)
        if not value:
            continue
        value = str(value).replace("\\", "/")
        aliases.add(Path(value).stem.lower().strip())
        aliases.add(Path(value).name.lower().strip())
    return {a for a in aliases if a}


def source_of(chunk: dict) -> str:
    aliases = source_aliases(chunk)
    return sorted(aliases)[0] if aliases else ""


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def pages_of(record: dict) -> list:
    pages = record.get("pages") or record.get("page_numbers") or []
    if isinstance(pages, (int, str)):
        pages = [pages]
    return pages


def evidence_matches(chunk: dict, evidence: dict) -> bool:
    expected_source = norm(evidence.get("source", ""))
    if not expected_source:
        return False

    aliases = source_aliases(chunk)
    # Compare exact normalized stem/name, not title alone.
    if expected_source not in aliases:
        return False

    expected_pages = set(evidence.get("pages") or [])
    chunk_pages = set(pages_of(chunk))
    if expected_pages and not (expected_pages & chunk_pages):
        return False

    required_text = evidence.get("contains")
    chunk_text = chunk.get("text") or chunk.get("content") or ""
    return not required_text or norm(required_text) in norm(chunk_text)


def read_jsonl_chunks(path: Path = CHUNKS_FILE) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Chunks file not found: {path}")
    chunks = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_no}: invalid JSON in chunks file: {exc.msg}"
                ) from exc
    log(f"Loaded {len(chunks)} indexed chunks from {path}")
    return chunks


def indexed_sources(chunks_file: Path = CHUNKS_FILE) -> set[str]:
    chunks = read_jsonl_chunks(chunks_file)
    all_aliases = set()
    for chunk in chunks:
        all_aliases.update(source_aliases(chunk))
    return all_aliases


def unwrap_hit(hit: dict) -> dict:
    """Support retrievers returning flattened payloads or {payload: {...}}."""
    payload = hit.get("payload")
    if isinstance(payload, dict):
        merged = dict(payload)
        merged.update({k: v for k, v in hit.items() if k not in {"payload"}})
        return merged
    return hit


def score_question(evidence: list[dict], hits: list[dict], k: int) -> dict:
    found_at = [None] * len(evidence)
    first_relevant = None
    dcg = 0.0

    for rank, raw_hit in enumerate(hits[:k], start=1):
        hit = unwrap_hit(raw_hit)
        newly_found = []
        for index, ev in enumerate(evidence):
            if found_at[index] is None and evidence_matches(hit, ev):
                found_at[index] = rank
                newly_found.append(index)

        if newly_found:
            first_relevant = first_relevant or rank
            dcg += 1 / math.log2(rank + 1)

    ideal = sum(
        1 / math.log2(rank + 1)
        for rank in range(1, min(len(evidence), k) + 1)
    )
    return {
        "hit": float(first_relevant is not None),
        "recall": sum(rank is not None for rank in found_at) / len(evidence),
        "mrr": 1 / first_relevant if first_relevant else 0.0,
        "ndcg": dcg / ideal if ideal else 0.0,
        "first_relevant_rank": first_relevant,
        "evidence_found_at": found_at,
    }


def aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, **{metric: 0.0 for metric in METRICS}}
    return {
        "n": len(rows),
        **{metric: round(mean(row[metric] for row in rows), 4) for metric in METRICS},
    }


def compact_hit(raw_hit: dict, rank: int) -> dict:
    hit = unwrap_hit(raw_hit)
    return {
        "rank": rank,
        "chunk_id": hit.get("id") or hit.get("chunk_id"),
        "score": round(float(hit.get("score", 0.0)), 6),
        "source": hit.get("source") or hit.get("source_id") or hit.get("title"),
        "pages": pages_of(hit),
        "text": hit.get("text") or hit.get("content") or "",
    }


def evaluate(
    questions: list[dict],
    retrieve: Retrieve,
    k: int,
    indexed: set[str],
) -> tuple[dict, dict]:
    scored, skipped, unanswerable = [], [], []
    human_review = []

    for number, question in enumerate(questions, start=1):
        qid = question.get("id", f"row-{number}")
        qtext = question.get("question", "")
        evidence = question.get("evidence") or []
        answer = question.get("answer")

        log(f"[{number}/{len(questions)}] {qid}: {qtext}")

        missing_sources = [
            ev.get("source")
            for ev in evidence
            if norm(ev.get("source", "")) not in indexed
        ]
        if evidence and missing_sources:
            log(f"  SKIPPED: evidence source(s) not found in indexed chunks: {missing_sources}")
            skipped.append({"id": qid, "missing_sources": missing_sources})
            human_review.append({
                "id": qid,
                "question": qtext,
                "expected_answer": answer,
                "expected_evidence": evidence,
                "status": "skipped_source_not_indexed",
                "retrieved_chunks": [],
                "human_verdict": "NOT REVIEWED - evidence source is not indexed",
                "review_notes": "",
            })
            continue

        raw_hits = retrieve(qtext, k)
        hits = [compact_hit(hit, rank) for rank, hit in enumerate(raw_hits[:k], start=1)]

        if not evidence:
            top1 = hits[0]["score"] if hits else None
            unanswerable.append({
                "id": qid,
                "question": qtext,
                "top1_score": top1,
                "top": hits[:3],
            })
            human_review.append({
                "id": qid,
                "question": qtext,
                "expected_answer": answer,
                "expected_evidence": [],
                "status": "unanswerable",
                "retrieved_chunks": hits,
                "human_verdict": "REVIEW WHETHER THESE RESULTS SHOULD BE REJECTED",
                "review_notes": "",
            })
            continue

        metrics = score_question(evidence, raw_hits, k)
        row = {
            "id": qid,
            "type": question.get("type"),
            "category": question.get("category"),
            "question": qtext,
            **metrics,
            "top": [
                {key: value for key, value in hit.items() if key != "text"}
                for hit in hits
            ],
        }
        scored.append(row)

        # Add an explicit match explanation for each retrieved chunk.
        for hit in hits:
            hit["matches_evidence"] = [
                i for i, ev in enumerate(evidence, start=1)
                if evidence_matches(hit, ev)
            ]

        status = "evidence_found" if metrics["hit"] else "evidence_not_found_in_top_k"
        log(
            f"  {status.upper()} | hit@{k}={metrics['hit']:.0f} "
            f"recall@{k}={metrics['recall']:.2f} "
            f"MRR={metrics['mrr']:.3f} | retrieved={len(hits)}"
        )
        for hit in hits:
            preview = re.sub(r"\s+", " ", hit["text"]).strip()
            log(
                f"    rank={hit['rank']} score={hit['score']:.4f} "
                f"source={hit['source']} pages={hit['pages']} "
                f"matches={hit['matches_evidence']}"
            )
            log(f"      TEXT: {preview[:500]}{'...' if len(preview) > 500 else ''}")

        human_review.append({
            "id": qid,
            "type": question.get("type"),
            "category": question.get("category"),
            "question": qtext,
            "expected_answer": answer,
            "expected_evidence": evidence,
            "retrieval_metrics": metrics,
            "status": status,
            "retrieved_chunks": hits,
            "human_verdict": "PENDING",
            "review_notes": "",
        })

    by_type = defaultdict(list)
    by_category = defaultdict(list)
    for row in scored:
        by_type[row["type"]].append(row)
        by_category[row["category"]].append(row)

    answerable_top1 = [row["top"][0]["score"] for row in scored if row["top"]]
    unanswerable_top1 = [
        row["top1_score"] for row in unanswerable
        if row["top1_score"] is not None
    ]

    report = {
        "k": k,
        "questions_loaded": len(questions),
        "questions_scored": len(scored),
        "questions_skipped": len(skipped),
        "questions_unanswerable": len(unanswerable),
        "overall": aggregate(scored),
        "by_type": {key: aggregate(rows) for key, rows in sorted(by_type.items())},
        "by_category": {
            key: aggregate(rows) for key, rows in sorted(by_category.items())
        },
        "top1_score": {
            "answerable_mean": round(mean(answerable_top1), 4) if answerable_top1 else None,
            "unanswerable_mean": round(mean(unanswerable_top1), 4) if unanswerable_top1 else None,
            "unanswerable_max": max(unanswerable_top1, default=None),
        },
        "skipped_not_indexed": skipped,
        "questions": scored,
        "unanswerable": unanswerable,
    }
    human_report = {
        "purpose": "Human validation of expected answers against retrieved chunks",
        "instructions": (
            "For each question, compare expected_answer with retrieved_chunks[].text. "
            "Check whether the retrieved text supports the answer, not merely whether "
            "the source/page matches. Fill human_verdict with PASS, FAIL, or PARTIAL "
            "and add review_notes."
        ),
        "k": k,
        "questions": human_review,
    }
    return report, human_report


def print_report(report: dict) -> None:
    k = report["k"]
    print("\n" + "=" * 78)
    print("RETRIEVAL EVALUATION SUMMARY")
    print("=" * 78)
    print(f"Questions loaded       : {report['questions_loaded']}")
    print(f"Questions scored       : {report['questions_scored']}")
    print(f"Skipped (not indexed)  : {report['questions_skipped']}")
    print(f"Unanswerable           : {report['questions_unanswerable']}")
    header = f"{'slice':<26}{'n':>5}{'hit@'+str(k):>10}{'recall@'+str(k):>11}{'mrr':>9}{'ndcg@'+str(k):>10}"
    print("\n" + header)
    print("-" * len(header))

    def print_line(name: str, agg: dict) -> None:
        if agg["n"]:
            print(
                f"{name:<26}{agg['n']:>5}{agg['hit']:>10.3f}"
                f"{agg['recall']:>11.3f}{agg['mrr']:>9.3f}{agg['ndcg']:>10.3f}"
            )

    print_line("overall", report["overall"])
    for name, agg in report["by_type"].items():
        print_line(f"type={name}", agg)
    for name, agg in report["by_category"].items():
        print_line(f"category={name}", agg)

    print("\n[NOTE] Retrieval metrics only measure evidence matching. They do not prove")
    print("       that the retrieved text fully supports the expected answer.")


def run(
    model: str = "BAAI/bge-small-en-v1.5",
    k: int = 10,
    tag: str | None = None,
    questions_file: Path = QUESTIONS_FILE,
    chunks_file: Path = CHUNKS_FILE,
) -> int:
    from studyrag.embedding.indexer import DenseRetriever

    if k < 1:
        raise ValueError("k must be >= 1")

    questions = load_questions(questions_file)
    chunks = read_jsonl_chunks(chunks_file)
    indexed = set()
    for chunk in chunks:
        indexed.update(source_aliases(chunk))

    log(f"Starting dense retrieval evaluation | k={k} | model={model}")
    log(f"Indexed source aliases: {len(indexed)}")

    retriever = DenseRetriever(model)
    started = time.perf_counter()
    try:
        report, human_report = evaluate(
            questions,
            lambda query, n: retriever.search(query, n),
            k,
            indexed,
        )
    finally:
        retriever.close()

    elapsed = round(time.perf_counter() - started, 2)
    report.update({
        "tag": tag,
        "model": model,
        "retriever": "dense",
        "questions_file": str(questions_file),
        "chunks_file": str(chunks_file),
        "seconds": elapsed,
    })
    human_report.update({
        "tag": tag,
        "model": model,
        "questions_file": str(questions_file),
        "seconds": elapsed,
    })

    print_report(report)

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    safe_tag = tag or time.strftime("dense_%Y%m%d_%H%M%S")
    metrics_path = RUNS_DIR / f"{safe_tag}.json"
    human_path = RUNS_DIR / f"{safe_tag}_human_validation.json"

    metrics_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    human_path.write_text(
        json.dumps(human_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log(f"Metrics saved to: {metrics_path}")
    log(f"Human validation file saved to: {human_path}")
    return 0


def compare(base: str, new: str) -> int:
    def load_run(tag_or_path: str):
        path = Path(tag_or_path)
        if not path.exists():
            path = RUNS_DIR / f"{tag_or_path}.json"
        return read_json(path, None)

    old, new_report = load_run(base), load_run(new)
    if old is None or new_report is None:
        print("Could not find one or both run files.")
        return 1

    print(f"{'slice':<26}{'n':>5}{'hit delta':>12}{'recall delta':>14}{'mrr delta':>11}{'ndcg delta':>12}")
    slices = [("overall", old["overall"], new_report["overall"])]
    for group in ("by_type", "by_category"):
        names = set(old.get(group, {})) | set(new_report.get(group, {}))
        for name in sorted(names):
            slices.append((
                f"{group[3:]}={name}",
                old.get(group, {}).get(name, {"n": 0}),
                new_report.get(group, {}).get(name, {"n": 0}),
            ))
    for name, a, b in slices:
        if not a.get("n") or not b.get("n"):
            continue
        print(
            f"{name:<26}{b['n']:>5}"
            f"{b['hit']-a['hit']:>12.3f}"
            f"{b['recall']-a['recall']:>14.3f}"
            f"{b['mrr']-a['mrr']:>11.3f}"
            f"{b['ndcg']-a['ndcg']:>12.3f}"
        )
    return 0


def check(
    questions_file: Path = QUESTIONS_FILE,
    chunks_file: Path = CHUNKS_FILE,
) -> int:
    questions = load_questions(questions_file)
    chunks = read_jsonl_chunks(chunks_file)
    indexed = set()
    for chunk in chunks:
        indexed.update(source_aliases(chunk))

    errors, ids, question_texts = [], set(), {}
    pending = 0

    for question in questions:
        qid = question.get("id", "?")
        missing_fields = {"id", "question", "type", "category", "answer"} - set(question)
        if missing_fields:
            errors.append(f"{qid}: missing fields {sorted(missing_fields)}")
        if qid in ids:
            errors.append(f"{qid}: duplicate id")
        ids.add(qid)

        normalized_question = norm(question.get("question", ""))
        if normalized_question in question_texts:
            errors.append(
                f"{qid}: duplicate question text (also appears in {question_texts[normalized_question]})"
            )
        else:
            question_texts[normalized_question] = qid

        if question.get("type") not in QUESTION_TYPES:
            errors.append(f"{qid}: unknown type {question.get('type')!r}")
        evidence = question.get("evidence") or []
        if question.get("type") == "unanswerable" and evidence:
            errors.append(f"{qid}: unanswerable question must have empty evidence")
        if question.get("type") != "unanswerable" and not evidence:
            errors.append(f"{qid}: answerable question has no evidence")

        for ev in evidence:
            if not ev.get("source"):
                errors.append(f"{qid}: evidence item missing source")
                continue
            if norm(ev["source"]) not in indexed:
                pending += 1
            elif not any(evidence_matches(chunk, ev) for chunk in chunks):
                errors.append(
                    f"{qid}: no chunk matches source/pages/contains criteria: {ev}"
                )

    print("\nQUESTION DATA VALIDATION")
    print(f"Questions loaded: {len(questions)}")
    print(f"Evidence items whose source is not indexed: {pending}")
    for error in errors:
        print(f"[ERROR] {error}")
    print("[OK] No structural issues found." if not errors else f"[FAILED] {len(errors)} issue(s)")
    return 1 if errors else 0
