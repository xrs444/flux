"""note-router: route Supernote .note files from the Private Cloud tree.

  Note/Personal/** -> VAULT_DIR/<rel>.md (+ PDF in VAULT_DIR/attachments)
  Note/Work/**     -> WORK_OUTBOX/<rel>.pdf + .html
  TODO lines       -> Vikunja tasks (one-way, sha256-deduped)

Parsing shells out to the documented `supernote-tool` CLI (supernotelib).
Text comes from real-time-recognition notebooks only (no OCR/LLM here).
Every .note is copied to RAW_BACKUP before parsing: the format is reverse
engineered and changes between firmware versions.
"""
import hashlib
import html
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger("note-router")

NOTES_ROOT = Path(os.environ.get("NOTES_ROOT", "/data"))
VAULT_DIR = Path(os.environ.get("VAULT_DIR", "/sync/vault"))
WORK_OUTBOX = Path(os.environ.get("WORK_OUTBOX", "/sync/work-outbox"))
RAW_BACKUP = Path(os.environ.get("RAW_BACKUP", "/sync/raw-backup"))
STATE_DB = os.environ.get("STATE_DB", "/sync/state.db")
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "60"))
# Skip files modified very recently: the device may still be uploading.
SETTLE_SECONDS = int(os.environ.get("SETTLE_SECONDS", "30"))
# Frontmatter dates use local time, not UTC: an evening note in Arizona
# would otherwise be stamped with tomorrow's date.
NOTE_TZ = ZoneInfo(os.environ.get("NOTE_TZ", "America/Phoenix"))
VIKUNJA_URL = os.environ.get("VIKUNJA_URL", "").rstrip("/")
VIKUNJA_PROJECT_ID = os.environ.get("VIKUNJA_PROJECT_ID", "")
VIKUNJA_TOKEN = os.environ.get("VIKUNJA_TOKEN", "")

TODO_RE = re.compile(r"^\s*(?:TODO|todo|To-?do)\s*[:\-]?\s+(.+?)\s*$")


def db() -> sqlite3.Connection:
    Path(STATE_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(STATE_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, sig TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS todos (hash TEXT PRIMARY KEY, task_id INTEGER)")
    conn.commit()
    return conn


def file_sig(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(p: Path):
    """Return ('work'|'personal', relative path under Note/<cat>) or None."""
    parts = p.relative_to(NOTES_ROOT).parts
    for i, part in enumerate(parts[:-1]):
        if part == "Note" and i + 1 < len(parts) - 1:
            cat = parts[i + 1].lower()
            if cat in ("work", "personal"):
                return cat, Path(*parts[i + 2:])
    return None


def tool(*args: str) -> str:
    r = subprocess.run(["supernote-tool", *args], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"supernote-tool {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def extract_text(note: Path, tmp: Path) -> str:
    out = tmp / "text.txt"
    tool("convert", "-t", "txt", "-a", "--text-page-separator=\n\n---\n\n", str(note), str(out))
    return out.read_text(errors="replace") if out.exists() else ""


def extract_pdf(note: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tool("convert", "-t", "pdf", "-a", str(note), str(out))


def extract_keywords(note: Path) -> list[str]:
    """Best effort: walk `analyze` JSON for keyword-ish entries."""
    try:
        data = json.loads(tool("analyze", str(note)))
    except Exception as e:  # noqa: BLE001 - metadata is optional
        log.warning("analyze failed for %s: %s", note.name, e)
        return []
    found: list[str] = []

    def walk(o, key=""):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            for v in o:
                walk(v, key)
        elif isinstance(o, str) and "keyword" in key.lower() and o.strip():
            found.append(o.strip())

    walk(data)
    return sorted({re.sub(r"\s+", "-", k.lower()) for k in found})


def push_todos(conn: sqlite3.Connection, text: str, source: str) -> None:
    if not (VIKUNJA_URL and VIKUNJA_PROJECT_ID and VIKUNJA_TOKEN):
        # Don't skip silently: an empty token once meant TODOs vanished with
        # no log line at all.
        if any(TODO_RE.match(line) for line in text.splitlines()):
            log.warning(
                "TODO lines found in %s but Vikunja is not configured "
                "(url/project/token missing) - skipping", source,
            )
        return
    for line in text.splitlines():
        m = TODO_RE.match(line)
        if not m:
            continue
        title = m.group(1)
        h = hashlib.sha256(title.lower().encode()).hexdigest()
        if conn.execute("SELECT 1 FROM todos WHERE hash=?", (h,)).fetchone():
            continue
        # Vikunja creates with PUT /projects/{id}/tasks.
        r = requests.put(
            f"{VIKUNJA_URL}/api/v1/projects/{VIKUNJA_PROJECT_ID}/tasks",
            headers={"Authorization": f"Bearer {VIKUNJA_TOKEN}"},
            json={"title": title, "description": f"From Supernote: {source}"},
            timeout=15,
        )
        r.raise_for_status()
        conn.execute("INSERT INTO todos VALUES (?, ?)", (h, r.json().get("id")))
        conn.commit()
        log.info("vikunja task created: %s", title)


def write_personal(note: Path, rel: Path, text: str, keywords: list[str], tmp: Path) -> None:
    stem = rel.with_suffix("")
    md_path = VAULT_DIR / stem.with_suffix(".md")
    pdf_rel = Path("attachments") / stem.with_suffix(".pdf")
    extract_pdf(note, VAULT_DIR / pdf_rel)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    mtime = datetime.fromtimestamp(note.stat().st_mtime, NOTE_TZ).strftime("%Y-%m-%d")
    tags = "\n".join(f"  - {k}" for k in ["supernote", *keywords])
    md_path.write_text(
        f"---\ndate: {mtime}\nsource: supernote\ntags:\n{tags}\n---\n\n"
        f"# {stem.name}\n\n{text.strip()}\n\n![[{pdf_rel.as_posix()}]]\n"
    )


def write_work(note: Path, rel: Path, text: str, keywords: list[str]) -> None:
    stem = rel.with_suffix("")
    extract_pdf(note, WORK_OUTBOX / stem.with_suffix(".pdf"))
    html_path = WORK_OUTBOX / stem.with_suffix(".html")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"<p>{html.escape(p)}</p>\n" for p in text.strip().split("\n\n") if p.strip())
    kw = f"<p><em>Keywords: {html.escape(', '.join(keywords))}</em></p>" if keywords else ""
    html_path.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(stem.name)}</title></head>"
        f"<body><h1>{html.escape(stem.name)}</h1>{kw}{body}</body></html>"
    )


def process(conn: sqlite3.Connection, note: Path) -> None:
    c = classify(note)
    if c is None:
        return
    cat, rel = c
    sig = file_sig(note)
    row = conn.execute("SELECT sig FROM files WHERE path=?", (str(note),)).fetchone()
    if row and row[0] == sig:
        return
    RAW_BACKUP.mkdir(parents=True, exist_ok=True)
    shutil.copy2(note, RAW_BACKUP / f"{sig[:16]}-{note.name}")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        text = extract_text(note, tmp)
        keywords = extract_keywords(note)
        if cat == "personal":
            write_personal(note, rel, text, keywords, tmp)
        else:
            write_work(note, rel, text, keywords)
        # TODO lines go to Vikunja regardless of category (capture-only).
        push_todos(conn, text, f"{cat}/{rel}")
    conn.execute("INSERT OR REPLACE INTO files VALUES (?, ?)", (str(note), sig))
    conn.commit()
    log.info("routed %s -> %s", rel, cat)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = db()
    while True:
        now = time.time()
        for note in NOTES_ROOT.rglob("*.note"):
            try:
                if now - note.stat().st_mtime < SETTLE_SECONDS:
                    continue
                process(conn, note)
            except Exception:  # noqa: BLE001 - one bad note must not stop the loop
                log.exception("failed on %s", note)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
