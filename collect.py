"""Run once a week (or daily): python collect.py

Fetches postings from all sources in config.py, extracts skills, stores new ones.
"""
import datetime as dt

from radar import db
from radar.collectors import collect_all, OK_PREFIXES
from radar.analysis import open_mask, board_runs, _ts
from radar import links
import config
from radar.skills import extract_skills


def check_links(conn, today: str):
    """Check links of open jobs (see radar/links.py). Runs 8 at a time."""
    import pandas as pd
    from concurrent.futures import ThreadPoolExecutor
    df = pd.read_sql("SELECT job_key, source, url, last_seen, link_status, link_checked FROM jobs", conn)
    df = df[open_mask(df, board_runs(conn))]
    recheck = (pd.Timestamp(today) - pd.Timedelta(days=getattr(config, "LINK_RECHECK_DAYS", 3))).date().isoformat()
    due = df.link_checked.isna() | (df.link_checked < recheck)
    company_site = df.source.eq("greenhouse") & ~df.url.map(links.is_greenhouse_hosted)
    wanted = df.source.eq("list") | company_site
    if getattr(config, "LINK_CHECK_ALL", False):
        wanted |= df.source.isin(["greenhouse", "lever", "ashby", "smartrecruiters", "workday", "remotive"])
    todo = df[due & wanted].head(getattr(config, "LINK_CHECK_MAX", 1500))
    if todo.empty:
        return
    print(f"Checking {len(todo):,} job links ...")
    with ThreadPoolExecutor(max_workers=getattr(config, "COLLECT_THREADS", 8)) as pool:
        results = list(pool.map(links.check_url, todo.url))
    dead = fixed = 0
    for (key, src, url), status in zip(todo[["job_key", "source", "url"]].itertuples(index=False), results):
        new_url = url
        if status == "dead" and src == "greenhouse" and links.backup_url(key):
            new_url, status = links.backup_url(key), "ok"      # company link broken, job still open
            fixed += 1
        elif status == "dead":
            dead += 1
        conn.execute("UPDATE jobs SET link_status = ?, link_checked = ?, url = ? WHERE job_key = ?",
                     (status, today, new_url, key))
    conn.commit()
    unknown = sum(r == "unknown" for r in results)
    print(f"  links: {len(todo) - dead - unknown - fixed:,} OK, {dead:,} dead (hidden), {fixed:,} switched to the "
          f"Greenhouse copy, {unknown:,} couldn't be checked (site blocks checks)")


def save_derived(conn):
    """Work out level / years / flags for new jobs (or all jobs after a rules change) and save them,
    so the dashboard never has to read every description when it starts."""
    from radar.analysis import RULES_VERSION, derive
    rows = conn.execute(
        "SELECT job_key, title, description, seniority FROM jobs WHERE rules_version IS NULL "
        "OR (rules_version < ? AND description != '')", (RULES_VERSION,)).fetchall()
    if not rows:
        return
    print(f"Reading {len(rows):,} job descriptions for level / sponsorship / experience ...")
    conn.executemany("UPDATE jobs SET level = ?, min_years = ?, work_auth = ?, rules_version = ? WHERE job_key = ?",
                     [(*derive(t, d, s), RULES_VERSION, k) for k, t, d, s in rows])
    conn.commit()


def main():
    today = dt.date.today().isoformat()
    run_ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")   # tells same-day runs apart
    conn = db.connect()
    new = seen = 0
    print(f"Collecting postings for {today} ...")
    for job in collect_all():
        skills = extract_skills(f"{job['title']} {job['description']}")
        if db.upsert_job(conn, job, skills, run_ts):
            new += 1
        else:
            seen += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    import pandas as pd
    db.mark_boards_ok(conn, OK_PREFIXES, run_ts)
    conn.commit()
    save_derived(conn)
    if getattr(config, "LINK_CHECK", True):
        check_links(conn, today)
    df = pd.read_sql("SELECT job_key, source, last_seen, link_status FROM jobs", conn)
    is_open = open_mask(df, board_runs(conn))
    df["last_seen"] = _ts(df["last_seen"])
    closed = int((~is_open).sum())
    # keep the database small: drop the long description text of jobs closed for 30+ days
    # (their skills, dates and flags stay, so trends and charts are unaffected)
    old = df[~is_open & (df.last_seen < pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=30))]
    if len(old):
        conn.executemany("UPDATE jobs SET description = '' WHERE job_key = ? AND description != ''",
                         [(k,) for k in old.job_key])
        conn.commit()
        conn.execute("VACUUM")
    print(f"Done: {new} new, {seen} still open, {closed} closed since earlier runs, {total} total in database.")


if __name__ == "__main__":
    main()
