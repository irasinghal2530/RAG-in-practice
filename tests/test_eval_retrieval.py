import json
import math

import pytest

from studyrag.evals.retrieval import check, evaluate, matches, score


def chunk(id_: str, title: str = "abb_lv", pages=(7,), text: str = "Insulation resistance, corrected to 25 C") -> dict:
    return {"id": id_, "title": title, "source": f"{title}.pdf", "pages": list(pages), "text": text, "score": 0.5}


EV = {"source": "abb_lv", "pages": [7], "contains": "CORRECTED  to 25"}


def test_match_needs_source_page_and_text():
    assert matches(chunk("a"), EV)  # case and whitespace insensitive
    assert not matches(chunk("a", title="baldor"), EV)
    assert not matches(chunk("a", pages=(8,)), EV)
    assert not matches(chunk("a", text="oven dried"), EV)
    assert matches(chunk("a", pages=(8,)), {"source": "abb_lv"})  # pages and contains are optional


def test_falls_back_to_source_filename_without_title():
    hit = chunk("a") | {"title": None}
    assert matches(hit, EV)


def test_score_first_hit_at_rank_two():
    hits = [chunk("x", title="baldor"), chunk("a"), chunk("b")]
    s = score([EV], hits, k=10)
    assert s["hit"] == 1 and s["recall"] == 1 and s["mrr"] == 0.5
    assert s["ndcg"] == pytest.approx(1 / math.log2(3))  # only the first relevant chunk earns gain


def test_score_partial_recall_and_cutoff():
    other = {"source": "brook", "pages": [4]}
    hits = [chunk("a"), chunk("x", title="baldor"), chunk("b", title="brook", pages=(4,))]
    assert score([EV, other], hits, k=2)["recall"] == 0.5
    full = score([EV, other], hits, k=3)
    assert full["recall"] == 1 and full["evidence_found_at"] == [1, 3]
    assert full["ndcg"] == pytest.approx((1 + 1 / 2) / (1 + 1 / math.log2(3)))


def test_score_miss():
    assert score([EV], [chunk("x", title="baldor")], k=10) | {"evidence_found_at": None} == {
        "hit": 0.0, "recall": 0.0, "mrr": 0.0, "ndcg": 0.0, "first_relevant_rank": None, "evidence_found_at": None}


def test_evaluate_slices_skips_unindexed_and_scores_unanswerable():
    questions = [
        {"id": "q1", "type": "numeric_spec", "category": "manuals", "question": "ir?", "evidence": [EV]},
        {"id": "q2", "type": "procedure", "category": "manuals", "question": "dry?",
         "evidence": [{"source": "abb_lv", "contains": "oven"}]},
        {"id": "q3", "type": "procedure", "category": "drives", "question": "fault?",
         "evidence": [{"source": "acs580", "pages": [420]}]},
        {"id": "q4", "type": "unanswerable", "category": "none", "question": "price?", "evidence": []},
    ]
    report = evaluate(questions, lambda q, k: [chunk("a")], k=5, indexed={"abb_lv"})
    assert report["overall"] == {"n": 2, "hit": 0.5, "recall": 0.5, "mrr": 0.5, "ndcg": 0.5}
    assert report["by_type"]["numeric_spec"]["hit"] == 1 and report["by_type"]["procedure"]["hit"] == 0
    assert report["skipped_not_indexed"] == ["q3"]
    assert report["unanswerable"][0]["top1_score"] == 0.5


def test_check_flags_bad_questions(tmp_path, capsys):
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text(json.dumps(chunk("a")) + "\n", encoding="utf-8")
    questions = tmp_path / "q.jsonl"
    rows = [{"id": "q1", "type": "numeric_spec", "category": "manuals", "question": "?", "evidence": [EV]},
            {"id": "q1", "type": "nonsense", "category": "manuals", "question": "?",
             "evidence": [{"source": "abb_lv", "contains": "not there"}]},
            {"id": "q3", "type": "procedure", "category": "drives", "question": "?",
             "evidence": [{"source": "acs580"}]}]
    questions.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert check(questions, chunks) == 1
    out = capsys.readouterr().out
    assert "duplicate id" in out and "unknown type" in out and "no chunk matches" in out
    assert "1 evidence items in sources not indexed yet" in out
