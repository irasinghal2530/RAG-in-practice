"""
Downloads every source in sources.py into data/raw/<category>/.

Every file is recorded in data/raw/manifest.json with its source URL, sha256, download
time and a licence note. Commit the manifest, NOT the PDFs (most manuals are OEM copyright).
"""

import logging
import shutil
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import requests

from studyrag.config import DATA_DIR, RAW_DIR, SOURCE_MANIFEST
from studyrag.ingestion.sources import CWRU_BASE, CWRU_LINK, CWRU_PAGES, SOURCES, UCI_ZIPS
from studyrag.utils import read_json, sha256, write_json

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
CATEGORIES = list(SOURCES) + ["sensors"]


def download(url: str, dest: Path, session: requests.Session, retries: int = 3) -> str:
    if dest.exists() and dest.stat().st_size > 0:
        return "skipped (exists)"
    for attempt in range(1, retries + 1):
        try:
            return _download_once(url, dest, session)
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError):
            if attempt == retries:
                raise
            time.sleep(5 * attempt)  # dropped connections on big files are usually transient
    raise AssertionError("unreachable")


def _download_once(url: str, dest: Path, session: requests.Session) -> str:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with session.get(url, stream=True, timeout=60, allow_redirects=True) as r:
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if dest.suffix == ".pdf" and "html" in ctype.lower():
            raise ValueError(f"got HTML instead of PDF ({ctype}) - open the URL in a browser")
        with tmp.open("wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    # some servers send PDFs as octet-stream and error pages as anything, so check the bytes
    if dest.suffix == ".pdf" and not tmp.read_bytes()[:1024].lstrip().startswith(b"%PDF"):
        tmp.unlink()
        raise ValueError("response is not a PDF - open the URL in a browser")
    tmp.replace(dest)
    return "downloaded"


def record(manifest: list, category: str, dest: Path, url: str, note: str) -> None:
    manifest.append({
        "category": category, "file": dest.relative_to(DATA_DIR.parent).as_posix(), "url": url,
        "sha256": sha256(dest), "note": note,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    })


def fetch_cwru(manifest: list, failures: list, session: requests.Session, pages: list) -> None:
    """Scrape the CWRU pages for .mat links so new files on their side are picked up."""
    for page in pages:
        html = session.get(CWRU_BASE + page, timeout=60).text
        links = CWRU_LINK.findall(html)
        if not links:
            failures.append((f"cwru/{page}", CWRU_BASE + page, "no .mat links found on page"))
            continue
        folder = RAW_DIR / "sensors" / "cwru" / page.replace("-bearing-fault-data", "").replace("-data", "")
        folder.mkdir(parents=True, exist_ok=True)
        new = 0
        for url, file_id, label in links:
            dest = folder / f"{label.strip().replace('@', 'at')}__{file_id}.mat"
            try:
                if download(url, dest, session) == "downloaded":
                    record(manifest, "sensors", dest, url,
                           "CWRU Bearing Data Center - free for research, cite CWRU")
                    new += 1
            except Exception as e:  # noqa: BLE001
                failures.append((dest.name, url, str(e)))
        log.info("[ok] CWRU %s: %d files (%d new)", page, len(links), new)


def fetch_uci_zip(manifest: list, session: requests.Session, folder: str, url: str, note: str) -> None:
    dest_dir = RAW_DIR / "sensors" / folder
    if dest_dir.exists() and any(dest_dir.iterdir()):
        log.info("[skip] %s already present", folder)
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    zpath = dest_dir.with_suffix(".zip")
    download(url, zpath, session)
    with zipfile.ZipFile(zpath) as zf:
        for member in zf.infolist():
            name = Path(member.filename).name  # flatten, and never write outside dest_dir
            if member.is_dir() or not name:
                continue
            out = dest_dir / name
            with zf.open(member) as src, out.open("wb") as f:
                shutil.copyfileobj(src, f)
            record(manifest, "sensors", out, url, note)
    zpath.unlink()
    log.info("[ok] %s -> %s", folder, dest_dir)


def run(only: list | None = None, skip_cwru_48k: bool = False) -> int:
    wanted = set(only) if only else set(CATEGORIES)
    session = requests.Session()
    session.headers["User-Agent"] = UA
    manifest = read_json(SOURCE_MANIFEST, [])
    failures = []

    for category, items in SOURCES.items():
        if category not in wanted:
            continue
        log.info("== %s ==", category)
        (RAW_DIR / category).mkdir(parents=True, exist_ok=True)
        for fname, url, note in items:
            dest = RAW_DIR / category / fname
            try:
                status = download(url, dest, session)
                log.info("[ok] %s: %s", fname, status)
                if status == "downloaded":
                    record(manifest, category, dest, url, note)
                time.sleep(1.5)  # be polite to government servers
            except Exception as e:  # noqa: BLE001
                failures.append((fname, url, str(e)))
                log.error("[FAIL] %s: %s", fname, e)

    if "sensors" in wanted:
        log.info("== sensors ==")
        for folder, url, note in UCI_ZIPS:
            try:
                fetch_uci_zip(manifest, session, folder, url, note)
            except Exception as e:  # noqa: BLE001
                failures.append((folder, url, str(e)))
                log.error("[FAIL] %s: %s", folder, e)
        pages = [p for p in CWRU_PAGES if not (skip_cwru_48k and p.startswith("48k"))]
        try:
            fetch_cwru(manifest, failures, session, pages)
        except Exception as e:  # noqa: BLE001
            failures.append(("cwru", CWRU_BASE, str(e)))
            log.error("[FAIL] CWRU: %s", e)
        log.info("[manual] Paderborn bearing data (motor current + vibration, ~20 GB):"
                 " https://mb.uni-paderborn.de/kat/forschung/kat-datacenter/bearing-datacenter")
        log.info("[manual] MaFaulDa (~13 GB): https://www02.smt.ufrj.br/~offshore/mfs/page_01.html")

    write_json(SOURCE_MANIFEST, manifest)
    log.info("Manifest: %s (%d files)", SOURCE_MANIFEST, len(manifest))
    if failures:
        log.error("%d failed - try these in a browser:", len(failures))
        for fname, url, err in failures:
            log.error("  %s\n    %s\n    %s", fname, unquote(url), err)
    return 1 if failures else 0
