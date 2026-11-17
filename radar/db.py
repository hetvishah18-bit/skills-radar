"""SQLite storage. One file per dataset (default data/radar.db), two tables."""
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("RADAR_DB", Path(__file__).resolve().parent.parent / "data" / "radar.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_key     TEXT PRIMARY KEY,      -- source:company:id
    source      TEXT NOT NULL,
    company     TEXT,
    title       TEXT,
    role        TEXT,                  -- which target role bucket it matched
    location    TEXT,
    url         TEXT,
    description TEXT,
    first_seen  TEXT NOT NULL,         -- ISO date the posting first appeared
    last_seen   TEXT NOT NULL,
    seniority   TEXT,                  -- optional: Entry level, Mid-Senior level, ...
    remote      INTEGER,               -- optional: 1 = remote allowed
    salary_usd  REAL,                  -- optional: annualized salary
    posted_at   TEXT                   -- when the company published it (UTC ISO, or a date)
);
CREATE TABLE IF NOT EXISTS job_skills (
    job_key TEXT NOT NULL REFERENCES jobs(job_key),
    skill   TEXT NOT NULL,
    PRIMARY KEY (job_key, skill)
);
CREATE TABLE IF NOT EXISTS board_runs (
    prefix  TEXT PRIMARY KEY,          -- e.g. greenhouse:stripe  (a company's job board)
    last_ok TEXT NOT NULL              -- last day this board was fetched successfully
);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);
CREATE INDEX IF NOT EXISTS idx_jobs_role ON jobs(role);
"""

OPTIONAL_COLS = {"seniority": "TEXT", "remote": "INTEGER", "salary_usd": "REAL", "posted_at": "TEXT",
                 "link_status": "TEXT", "link_checked": "TEXT",
                 "level": "TEXT", "min_years": "INTEGER", "work_auth": "TEXT", "rules_version": "INTEGER"}
COLS = ["job_key", "source", "company", "title", "role", "location", "url", "description",
        "first_seen", "last_seen", "seniority", "remote", "salary_usd", "posted_at"]


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    have = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    for col, typ in OPTIONAL_COLS.items():  # migrate databases created by v1
        if col not in have:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {typ}")
    return conn


def upsert_job(conn, job: dict, skills: set[str], seen_date: str) -> bool:
    """seen_date: the run's UTC timestamp ('2026-11-16T17:28:00Z'); a plain date also works."""
    """Insert a new job (returns True) or bump last_seen on an existing one (False)."""
    posted = job.get("posted_at")
    posted_day = posted[:10] if posted else None
    cur = conn.execute("SELECT 1 FROM jobs WHERE job_key = ?", (job["job_key"],))
    if cur.fetchone():
        # still open: bump last_seen; fill in the real posting time if we didn't have it before
        conn.execute("UPDATE jobs SET last_seen = ?, posted_at = COALESCE(posted_at, ?), "
                     "first_seen = CASE WHEN ? IS NOT NULL AND ? < first_seen THEN ? ELSE first_seen END "
                     "WHERE job_key = ?",
                     (seen_date, posted, posted_day, posted_day, posted_day, job["job_key"]))
        return False
    first = job.get("first_seen") or (min(posted_day, seen_date[:10]) if posted_day else seen_date[:10])
    row = {**job, "first_seen": first, "last_seen": seen_date}
    conn.execute(f"INSERT INTO jobs ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
                 [row.get(c) for c in COLS])
    conn.executemany("INSERT OR IGNORE INTO job_skills VALUES (?,?)",
                     [(job["job_key"], s) for s in skills])
    return True


def mark_boards_ok(conn, prefixes, day: str) -> None:
    """day: the run's UTC timestamp, so two runs on the same day are told apart."""
    conn.executemany("INSERT INTO board_runs VALUES (?, ?) ON CONFLICT(prefix) DO UPDATE SET last_ok = excluded.last_ok",
                     [(p, day) for p in prefixes])
