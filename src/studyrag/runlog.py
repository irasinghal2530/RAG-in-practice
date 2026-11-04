"""
Run log: one JSON line per pipeline stage in logs/runs.jsonl, plus a plain-text logs/studyrag.log.

    with runlog.stage("parse", model={...}, only=only) as s:
        s.count("parsed")                          # documents / chunks processed
        s.item(doc="x.pdf", seconds=12.3)          # optional per-document detail
        s.details["output"] = str(path)            # anything else worth keeping

Each record has: run_id (shared by all stages of one CLI call), operation, status
(success | partial | failed | interrupted), started_at / finished_at / seconds, counts,
warnings and errors (every WARNING/ERROR logged by any library while the stage ran, deduplicated),
the model(s) used, the stage parameters, a snapshot of config.py, package versions and git commit.
"""

import json
import logging
import subprocess
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from studyrag import config

log = logging.getLogger(__name__)

LOGS_DIR = config.PROJECT_ROOT / "logs"
RUNS_FILE = LOGS_DIR / "runs.jsonl"
TEXT_LOG = LOGS_DIR / "studyrag.log"

RUN_ID = uuid.uuid4().hex[:12]  # one per process: groups the stages of one CLI call
PACKAGES = ["docling", "docling-core", "transformers", "sentence-transformers", "qdrant-client", "torch"]


def setup_logging(verbose: bool = False) -> None:
    """Console + logs/studyrag.log; Python warnings.warn() calls are routed into logging too."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = f"%(asctime)s %(levelname)-7s [{RUN_ID}] %(name)s: %(message)s"
    file_handler = logging.FileHandler(TEXT_LOG, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt))
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    logging.getLogger().addHandler(file_handler)
    logging.captureWarnings(True)


class _Capture(logging.Handler):
    """Collects every WARNING+ record logged anywhere while a stage runs, counting repeats."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.seen: dict[tuple, int] = {}

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            msg += f" | {type(exc).__name__}: {exc}"
        key = (record.levelname, record.name, msg[:1000])
        self.seen[key] = self.seen.get(key, 0) + 1

    def entries(self, errors: bool) -> list[dict]:
        return [{"level": lvl, "logger": name, "message": msg, "count": n}
                for (lvl, name, msg), n in self.seen.items()
                if (lvl in ("ERROR", "CRITICAL")) == errors]


class Stage:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.items: list[dict] = []
        self.details: dict = {}

    def count(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    def item(self, **fields) -> None:
        self.items.append(fields)


def _config_snapshot() -> dict:
    return {k: str(v) if isinstance(v, Path) else v for k, v in vars(config).items() if k.isupper()}


@cache
def _versions() -> dict:
    out = {}
    for pkg in PACKAGES:
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            pass
    return out


@cache
def _git() -> dict:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=config.PROJECT_ROOT, capture_output=True,
                              text=True, timeout=5).stdout.strip()
    try:
        return {"commit": git("rev-parse", "--short", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.SubprocessError):
        return {}


@contextmanager
def stage(operation: str, model: dict | None = None, **params):
    """Time a pipeline stage and append its record to logs/runs.jsonl, whether it succeeds or not."""
    s = Stage()
    capture = _Capture()
    root = logging.getLogger()
    root.addHandler(capture)
    started = datetime.now().astimezone()
    t0 = time.perf_counter()
    status, failure = "success", None
    log.info("%s started", operation)
    try:
        yield s
    except KeyboardInterrupt:
        status, failure = "interrupted", {"type": "KeyboardInterrupt", "message": "", "traceback": ""}
        raise
    except Exception as e:
        status = "failed"
        failure = {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc()}
        raise
    finally:
        root.removeHandler(capture)
        errors = capture.entries(errors=True)
        if status == "success" and errors:
            status = "partial"  # finished, but something (e.g. one PDF) failed along the way
        seconds = round(time.perf_counter() - t0, 3)
        record = {
            "run_id": RUN_ID,
            "operation": operation,
            "status": status,
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "seconds": seconds,
            "counts": s.counts,
            "warnings": capture.entries(errors=False),
            "errors": errors,
            "exception": failure,
            "model": model or {},
            "params": params,
            "details": s.details,
            "items": s.items,
            "config": _config_snapshot(),
            "versions": _versions(),
            "git": _git(),
        }
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(RUNS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        log.info("%s %s in %.1fs %s (%d warnings, %d errors)", operation, status, seconds,
                 s.counts, len(record["warnings"]), len(errors))


def recent(n: int = 20) -> list[dict]:
    if not RUNS_FILE.exists():
        return []
    with open(RUNS_FILE, encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    return [json.loads(line) for line in lines[-n:]]
