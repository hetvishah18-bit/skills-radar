"""Analysis queries: demand share, week-over-week trends, rising/falling skills, resume gaps."""
import sqlite3

import pandas as pd

from radar.location import is_us
from radar.seniority import infer_level, min_years
from radar.flags import work_auth_flags, BLOCKING
from radar.skills import SKILL_CATEGORY, extract_skills


def load(conn: sqlite3.Connection) -> tuple[pd.DataFrame, pd.DataFrame]:
    have = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    opt = ", ".join(c if c in have else f"NULL AS {c}"
                    for c in ("seniority", "remote", "salary_usd", "posted_at", "link_status"))
    jobs = pd.read_sql("SELECT job_key, source, company, title, role, location, url, first_seen, last_seen, "
                       f"{opt}, description FROM jobs", conn)   # older databases may lack the newer columns
    skills = pd.read_sql("SELECT job_key, skill FROM job_skills", conn)
    if jobs.empty:
        return jobs, skills
    jobs["first_seen"] = pd.to_datetime(jobs["first_seen"])
    jobs["last_seen"] = _ts(jobs["last_seen"])
    jobs["is_open"] = open_mask(jobs, board_runs(conn))
    # when the company posted it: exact UTC time when the source gives one, else the day
    pa = jobs["posted_at"].fillna("")
    jobs["posted_exact"] = pa.str.len() > 10
    jobs["posted_ts"] = pd.to_datetime(pa.where(pa != "", jobs["first_seen"].dt.strftime("%Y-%m-%d")),
                                       utc=True, errors="coerce", format="mixed")
    jobs["level"] = [infer_level(t, d, s) for t, d, s in zip(jobs.title, jobs.description, jobs.seniority)]
    jobs["min_years"] = jobs.description.map(min_years)
    flags = jobs.description.map(work_auth_flags)
    jobs["work_auth"] = flags.map(lambda f: ", ".join(f))
    jobs["auth_blocked"] = flags.map(lambda f: bool(BLOCKING & set(f)))
    jobs = jobs.drop(columns="description")
    jobs["is_us"] = jobs["location"].map(is_us) | (jobs["source"] == "linkedin_kaggle")  # that dataset is US-only
    # week bucket = Monday of the week the posting was first seen
    jobs["week"] = jobs["first_seen"].dt.to_period("W-SUN").dt.start_time
    skills["category"] = skills["skill"].map(SKILL_CATEGORY)
    return jobs, skills


def skill_share(jobs: pd.DataFrame, skills: pd.DataFrame) -> pd.DataFrame:
    """% of postings that mention each skill."""
    total = len(jobs)
    if not total:
        return pd.DataFrame(columns=["skill", "category", "postings", "share"])
    s = skills[skills.job_key.isin(jobs.job_key)]
    out = s.groupby(["skill", "category"]).job_key.nunique().reset_index(name="postings")
    out["share"] = out.postings / total
    return out.sort_values("share", ascending=False).reset_index(drop=True)


def weekly_share(jobs: pd.DataFrame, skills: pd.DataFrame) -> pd.DataFrame:
    """Long table: week, skill, share of that week's postings mentioning the skill."""
    if jobs.empty:
        return pd.DataFrame(columns=["week", "skill", "share"])
    per_week = jobs.groupby("week").job_key.nunique().rename("n_jobs")
    m = skills.merge(jobs[["job_key", "week"]], on="job_key")
    counts = m.groupby(["week", "skill"]).job_key.nunique().rename("n").reset_index()
    counts = counts.join(per_week, on="week")
    counts["share"] = counts.n / counts.n_jobs
    return counts[["week", "skill", "share", "n", "n_jobs"]]


def movers(jobs: pd.DataFrame, skills: pd.DataFrame, window_weeks: int = 4,
           min_postings: int = 10) -> pd.DataFrame:
    """Compare skill share in the latest `window_weeks` vs the previous `window_weeks`."""
    weeks = sorted(jobs.week.unique())
    if len(weeks) < 2:
        return pd.DataFrame(columns=["skill", "category", "before", "now", "change_pts"])
    w = min(window_weeks, len(weeks) // 2)
    recent, prior = weeks[-w:], weeks[-2 * w:-w]
    a = skill_share(jobs[jobs.week.isin(prior)], skills).set_index("skill")
    b = skill_share(jobs[jobs.week.isin(recent)], skills).set_index("skill")
    df = pd.DataFrame({"before": a.share, "now": b.share}).fillna(0)
    df["postings_now"] = b.postings.reindex(df.index).fillna(0).astype(int)
    df = df[(df.postings_now >= min_postings) | (a.postings.reindex(df.index).fillna(0) >= min_postings)]
    df["change_pts"] = (df.now - df.before) * 100
    df["category"] = df.index.map(SKILL_CATEGORY)
    return df.reset_index(names="skill").sort_values("change_pts", ascending=False)


def resume_gap(resume_text: str, jobs: pd.DataFrame, skills: pd.DataFrame,
               top_n: int = 20) -> tuple[set[str], pd.DataFrame]:
    """Which of the market's top skills are (not) on the resume, weighted by demand."""
    have = extract_skills(resume_text)
    top = skill_share(jobs, skills).head(top_n).copy()
    top["on_resume"] = top.skill.isin(have)
    return have, top


def coverage_score(gap_table: pd.DataFrame) -> float:
    """Demand-weighted % of top skills the resume covers (0-100)."""
    if gap_table.empty:
        return 0.0
    return 100 * gap_table.loc[gap_table.on_resume, "share"].sum() / gap_table.share.sum()


def salary_by_skill(jobs: pd.DataFrame, skills: pd.DataFrame, min_postings: int = 25) -> pd.DataFrame:
    """Median salary of postings that mention each skill vs. those that don't."""
    paid = jobs[jobs.salary_usd.notna()][["job_key", "salary_usd"]]
    if paid.empty:
        return pd.DataFrame(columns=["skill", "category", "with_skill", "without_skill", "premium", "n"])
    rows = []
    for skill, keys in skills[skills.job_key.isin(paid.job_key)].groupby("skill").job_key:
        has = paid.job_key.isin(set(keys))
        if has.sum() >= min_postings and (~has).sum() >= min_postings:
            w, wo = paid.salary_usd[has].median(), paid.salary_usd[~has].median()
            rows.append({"skill": skill, "category": SKILL_CATEGORY.get(skill), "with_skill": w,
                         "without_skill": wo, "premium": w / wo - 1, "n": int(has.sum())})
    return pd.DataFrame(rows).sort_values("with_skill", ascending=False).reset_index(drop=True)


def posted_within(jobs: pd.DataFrame, hours: float, now: pd.Timestamp | None = None) -> pd.Series:
    """True for postings published in the last `hours`. Day-only dates count if they fall on/after the cutoff day."""
    now = now or pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(hours=hours)
    exact = jobs.posted_exact & (jobs.posted_ts >= cutoff)
    day_only = ~jobs.posted_exact & (jobs.posted_ts.dt.normalize() >= cutoff.normalize())
    return exact | day_only


def posted_label(ts: pd.Timestamp, exact: bool, now: pd.Timestamp | None = None) -> str:
    if pd.isna(ts):
        return ""
    now = now or pd.Timestamp.now(tz="UTC")
    if exact:
        h = (now - ts).total_seconds() / 3600
        return "just now" if h < 1 else f"{int(h)}h ago" if h < 24 else f"{int(h // 24)}d ago"
    d = (now.normalize() - ts.normalize()).days
    return "today" if d <= 0 else "yesterday" if d == 1 else f"{d}d ago"


def _ts(values) -> pd.Series:
    """Dates ('2026-11-15') and timestamps ('2026-11-16T17:28:00Z') -> UTC timestamps."""
    return pd.to_datetime(pd.Series(values).astype(str), utc=True, format="mixed", errors="coerce")


def board_runs(conn) -> pd.Series:
    """prefix -> last day the company's board was fetched successfully (empty for old databases)."""
    try:
        r = pd.read_sql("SELECT prefix, last_ok FROM board_runs", conn)
        out = _ts(r.last_ok)
        out.index = r.prefix.values
        return out
    except Exception:
        return pd.Series(dtype="datetime64[ns, UTC]")


def open_mask(df: pd.DataFrame, runs: pd.Series | None = None) -> pd.Series:
    """Still open = seen in the latest successful check of its company's board.
    A board that fails one day doesn't close anything; a board that comes back empty closes its jobs.
    Workday is searched by keyword, so give it 7 days. One-off datasets are always 'open'."""
    last_seen = _ts(df["last_seen"]).set_axis(df.index)
    board = df["job_key"].str.rsplit(":", n=1).str[0]
    latest = last_seen.groupby(board).transform("max")
    if runs is not None and len(runs):
        latest = pd.concat([latest, board.map(runs)], axis=1).max(axis=1)
    grace = pd.to_timedelta(df["source"].eq("workday").map({True: 7, False: 0}), unit="D")
    snapshot = df["source"].isin(["linkedin_kaggle", "demo"])
    dead_link = (df["source"] == "list") & (df.get("link_status", pd.Series(index=df.index, dtype=object)) == "dead")
    return ((last_seen >= latest - grace) | snapshot) & ~dead_link
