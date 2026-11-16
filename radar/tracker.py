"""Application tracker: your own pipeline of jobs, kept in its own file (data/tracker.db)
so re-importing or re-collecting postings never touches it. Stays on your computer.
"""
import datetime as dt
import os
import sqlite3
from pathlib import Path

import pandas as pd

TRACKER_PATH = Path(os.environ.get("TRACKER_DB",
                                   Path(__file__).resolve().parent.parent / "data" / "tracker.db"))
BACKUP_DIR = TRACKER_PATH.parent / "tracker_backups"
KEEP_BACKUPS = 50
STATUSES = ["Saved", "Applied", "Interviewing", "Offer", "Rejected", "Withdrawn"]
ACTIVE = {"Saved", "Applied", "Interviewing"}
FOLLOW_UP_DAYS = 7

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key      TEXT UNIQUE,          -- link back to the radar posting (NULL for jobs added by hand)
    title        TEXT NOT NULL,
    company      TEXT,
    location     TEXT,
    url          TEXT,
    status       TEXT NOT NULL DEFAULT 'Saved',
    match_score  REAL,
    work_auth    TEXT,
    date_saved   TEXT,
    date_applied TEXT,
    follow_up    TEXT,
    notes        TEXT
);
"""
COLS = ["id", "job_key", "title", "company", "location", "url", "status", "match_score", "work_auth",
        "date_saved", "date_applied", "follow_up", "notes"]
DATE_COLS = ["date_saved", "date_applied", "follow_up"]


def connect(path: Path = TRACKER_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def backup(path: Path = TRACKER_PATH) -> Path | None:
    """Save a timestamped copy of every tracked job (JSON) before any change. Keeps the last 50."""
    import json
    path = Path(path)
    if not path.exists():
        return None
    with connect(path) as conn:
        rows = [dict(zip(COLS, r)) for r in conn.execute(f"SELECT {', '.join(COLS)} FROM applications")]
    if not rows:
        return None
    bdir = path.parent / "tracker_backups"
    bdir.mkdir(parents=True, exist_ok=True)
    out = bdir / f"tracker-{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
    out.write_text(json.dumps(rows, indent=1))
    for old in sorted(bdir.glob("tracker-*.json"))[:-KEEP_BACKUPS]:
        old.unlink()
    return out


def list_backups(path: Path = TRACKER_PATH) -> list[Path]:
    return sorted((Path(path).parent / "tracker_backups").glob("tracker-*.json"), reverse=True)


def restore(backup_file: Path, path: Path = TRACKER_PATH) -> int:
    """Put back every job from a backup that isn't in the tracker now (nothing is overwritten)."""
    import json
    backup(path)
    rows = json.loads(Path(backup_file).read_text())
    added = 0
    with connect(path) as conn:
        have_ids = {r[0] for r in conn.execute("SELECT id FROM applications")}
        have_keys = {r[0] for r in conn.execute("SELECT job_key FROM applications WHERE job_key IS NOT NULL")}
        for r in rows:
            if r["id"] in have_ids or (r.get("job_key") and r["job_key"] in have_keys):
                continue
            cols = [c for c in COLS if c != "id"]
            conn.execute(f"INSERT INTO applications ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                         [r.get(c) for c in cols])
            added += 1
    return added


def version(path: Path = TRACKER_PATH) -> str:
    """Changes whenever the saved data changes (used to reset the table editor)."""
    with connect(path) as conn:
        n, mx = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM applications").fetchone()
    mtime = Path(path).stat().st_mtime_ns if Path(path).exists() else 0
    return f"{n}-{mx}-{mtime}"


def add(job: dict, path: Path = TRACKER_PATH) -> bool:
    """Save a job. Returns False if it's already in the tracker."""
    backup(path)
    with connect(path) as conn:
        if job.get("job_key") and conn.execute("SELECT 1 FROM applications WHERE job_key=?",
                                               (job["job_key"],)).fetchone():
            return False
        conn.execute(
            "INSERT INTO applications (job_key, title, company, location, url, status, match_score, work_auth,"
            " date_saved, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (job.get("job_key"), job.get("title") or "Untitled job", job.get("company"), job.get("location"),
             job.get("url"), job.get("status", "Saved"), job.get("match_score"), job.get("work_auth"),
             dt.date.today().isoformat(), job.get("notes", "")))
    return True


def load(path: Path = TRACKER_PATH) -> pd.DataFrame:
    with connect(path) as conn:
        df = pd.read_sql(f"SELECT {', '.join(COLS)} FROM applications ORDER BY id DESC", conn)
    for c in DATE_COLS:
        df[c] = pd.Series([d.date() if pd.notna(d) else None
                           for d in pd.to_datetime(df[c], errors="coerce")], index=df.index, dtype=object)
    return df


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
        return None
    if isinstance(v, (dt.date, pd.Timestamp)):
        return pd.Timestamp(v).date().isoformat()
    return v


def to_delete(edited: pd.DataFrame, path: Path = TRACKER_PATH) -> pd.DataFrame:
    """Saved jobs that are missing from the edited table (i.e. would be deleted)."""
    now = load(path)
    keep = {int(i) for i in edited["id"].dropna()} if "id" in edited else set()
    return now[~now["id"].isin(keep)]


def save(edited: pd.DataFrame, path: Path = TRACKER_PATH, allow_delete: bool = False) -> int:
    """Write back an edited table: updates changed rows, inserts new ones, and (only if allow_delete)
    deletes removed ones. Always backs up first. Returns how many jobs were deleted.
    Auto-fills date_applied (today) and follow_up (+7 days) when a job moves to Applied."""
    today = dt.date.today()
    backup(path)
    with connect(path) as conn:
        existing = {r[0] for r in conn.execute("SELECT id FROM applications")}
        kept = set()
        for row in edited.to_dict("records"):
            status = row.get("status") or "Saved"
            if status in ("Applied", "Interviewing") and not _clean(row.get("date_applied")):
                row["date_applied"] = today
            if status == "Applied" and not _clean(row.get("follow_up")):
                row["follow_up"] = (pd.Timestamp(row["date_applied"]).date() + dt.timedelta(days=FOLLOW_UP_DAYS))
            vals = {c: _clean(row.get(c)) for c in COLS if c != "id"}
            vals["status"], vals["title"] = status, vals.get("title") or "Untitled job"
            rid = _clean(row.get("id"))
            if rid is not None and int(rid) in existing:
                rid = int(rid)
                kept.add(rid)
                conn.execute(f"UPDATE applications SET {', '.join(f'{c}=?' for c in vals)} WHERE id=?",
                             [*vals.values(), rid])
            elif vals.get("title") and (vals.get("company") or vals.get("url") or row.get("title")):
                vals.setdefault("date_saved", today.isoformat())
                vals["date_saved"] = vals["date_saved"] or today.isoformat()
                conn.execute(f"INSERT INTO applications ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})",
                             list(vals.values()))
        gone = existing - kept
        if allow_delete:
            for rid in gone:
                conn.execute("DELETE FROM applications WHERE id=?", (rid,))
    return len(gone) if allow_delete else 0


def due_followups(df: pd.DataFrame, today: dt.date | None = None) -> pd.DataFrame:
    today = today or dt.date.today()
    if df.empty:
        return df
    fu = pd.to_datetime(df.follow_up, errors="coerce")
    m = df.status.isin(ACTIVE) & fu.notna() & (fu <= pd.Timestamp(today))
    return df[m]
