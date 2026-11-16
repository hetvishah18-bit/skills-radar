"""Weekly email digest: new postings that fit your filters, ranked by how well they match your resume.

    python digest.py --dry-run          # writes data/digest.html, sends nothing (try this first)
    python digest.py                    # sends the email (needs the Gmail settings below)

Email settings come from environment variables (never put passwords in code):
    GMAIL_ADDRESS        the Gmail account that sends the digest
    GMAIL_APP_PASSWORD   a Gmail *App Password* (Google Account > Security > App passwords; needs 2-Step Verification)
    DIGEST_TO            where to send it (optional; defaults to GMAIL_ADDRESS)
Your resume: config.RESUME_PATH (e.g. data/resume.pdf) or the RESUME_TEXT environment variable.
"""
import argparse
import datetime as dt
import html
import os
import smtplib
import sqlite3
import sys
from email.message import EmailMessage
from pathlib import Path

import pandas as pd

import config
from radar import analysis as A
from radar import db
from radar import tailor as T
from radar.flags import BLOCKING
from radar.resume_io import load_resume

ROOT = Path(__file__).resolve().parent


def build(db_path: Path, days: int, resume: str) -> tuple[pd.DataFrame, dict]:
    with sqlite3.connect(db_path) as conn:
        jobs, skills = A.load(conn)
        if jobs.empty:
            return jobs, {"new": 0}
        since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
        new = jobs[A.posted_within(jobs, days * 24) & jobs.is_open]
        stats = {"new": len(new), "since": "the last 24 hours" if days == 1 else f"{since.date()}"}
        f = new
        if getattr(config, "DIGEST_ROLES", None):
            f = f[f.role.isin(config.DIGEST_ROLES)]
        if getattr(config, "DIGEST_US_ONLY", True):
            f = f[f.is_us]
        if getattr(config, "DIGEST_EARLY_CAREER_ONLY", True):
            f = f[f.level == "Early career"]
        if getattr(config, "DIGEST_HIDE_NO_SPONSOR", False):
            f = f[~f.auth_blocked]
        stats["matching"] = len(f)
        if f.empty:
            return f, stats
        desc = dict(conn.execute(
            f"SELECT job_key, description FROM jobs WHERE job_key IN ({','.join('?' * len(f))})",
            list(f.job_key)).fetchall())
        idf = T.build_idf(d for (d,) in conn.execute("SELECT description FROM jobs LIMIT 5000"))
    rows = []
    for r in f.itertuples():
        jd = desc.get(r.job_key, "")
        if resume:
            rep = T.match(resume, jd, idf=idf)
            rows.append((r.job_key, round(rep.score), ", ".join(sorted(rep.missing)[:4])))
        else:
            rows.append((r.job_key, None, ""))
    sc = pd.DataFrame(rows, columns=["job_key", "match", "missing"])
    out = f.merge(sc, on="job_key")
    out = (out.sort_values(["match", "posted_ts"], ascending=False, na_position="last") if resume
           else out.sort_values("posted_ts", ascending=False))
    # most common missing skills across the matching postings = what to learn next
    if resume:
        miss = out.missing.str.split(", ").explode().replace("", pd.NA).dropna().value_counts().head(5)
        stats["learn_next"] = list(miss.index)
    return out, stats


def render_html(top: pd.DataFrame, stats: dict, total: int, ranked_by_resume: bool = True) -> str:
    e = html.escape
    td = "<td style='padding:8px;border-bottom:1px solid #eee"
    rows = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #eee'>"
        f"<a href='{e(r.url or '#')}' style='color:#1a56db;font-weight:600;text-decoration:none'>{e(r.title)}</a><br>"
        f"<span style='color:#555'>{e(str(r.company))} · {e(str(r.location or ''))}</span>"
        + (f"<br><span style='color:#b45309;font-size:12px'>⚠ {e(r.work_auth)}</span>" if r.work_auth else "")
        + "</td>"
        + (f"{td};text-align:center;font-size:18px;font-weight:700'>{'' if pd.isna(r.match) else int(r.match)}</td>"
           f"{td};color:#b91c1c;font-size:13px'>{e(r.missing or '')}</td>" if ranked_by_resume else
           f"{td};color:#555;font-size:13px'>{e(str(r.level))}<br>{A.posted_label(r.posted_ts, r.posted_exact)}</td>")
        + "</tr>"
        for r in top.itertuples())
    learn = (f"<p><b>Skills these jobs ask for that your resume doesn't show:</b> {e(', '.join(stats['learn_next']))}</p>"
             if stats.get("learn_next") else "")
    filters = []
    if getattr(config, "DIGEST_EARLY_CAREER_ONLY", True): filters.append("early career")
    if getattr(config, "DIGEST_US_ONLY", True): filters.append("USA")
    if getattr(config, "DIGEST_HIDE_NO_SPONSOR", False): filters.append("sponsorship-friendly")
    head = ('<th style="padding:8px">Match</th><th style="padding:8px;text-align:left">Missing skills</th>'
            if ranked_by_resume else '<th style="padding:8px;text-align:left">Level · posted</th>')
    note = ("Match = how well your resume covers the posting's skills and key words (0-100). "
            if ranked_by_resume else "")
    return f"""<html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:760px;margin:auto;color:#111">
<h2 style="margin-bottom:4px">📡 Skills Radar {stats.get('label', 'weekly')} digest</h2>
<p style="color:#555;margin-top:0">{stats['new']:,} new postings since {stats['since']} ·
{stats['matching']:,} fit your filters ({', '.join(filters) or 'none'}) ·
{f"top {len(top)} by resume match below" if ranked_by_resume else f"newest {len(top)} below"}</p>
{learn}
<table style="border-collapse:collapse;width:100%">
<tr style="background:#f3f4f6"><th style="padding:8px;text-align:left">Job</th>{head}</tr>{rows}</table>
<p style="color:#777;font-size:12px">{note}⚠ = the posting mentions sponsorship, citizenship or clearance limits.
Always confirm details on the posting.</p>
</body></html>"""


def render_text(top: pd.DataFrame, stats: dict) -> str:
    lines = [f"Skills Radar weekly digest: {stats['new']} new postings, {stats['matching']} fit your filters.", ""]
    for r in top.itertuples():
        m = "" if pd.isna(r.match) else f"[{int(r.match)}] "
        lines.append(f"{m}{r.title} - {r.company} ({r.location})\n    {r.url}"
                     + (f"\n    ! {r.work_auth}" if r.work_auth else ""))
    return "\n".join(lines)


def send(subject: str, html_body: str, text_body: str):
    sender, pwd = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    if not (sender and pwd):
        sys.exit("Missing GMAIL_ADDRESS / GMAIL_APP_PASSWORD environment variables (see top of digest.py). "
                 "Use --dry-run to preview without sending.")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, os.environ.get("DIGEST_TO", sender)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(sender, pwd)
        s.send_message(msg)
    print(f"Sent digest to {msg['To']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=None, help="look back this many days (default: 1 if daily, 7 if weekly)")
    ap.add_argument("--auto", action="store_true",
                    help="for the scheduled job: send daily, or only on Mondays when DIGEST_FREQUENCY = 'weekly'")
    ap.add_argument("--dry-run", action="store_true", help="write data/digest.html instead of emailing")
    ap.add_argument("--db", default=os.environ.get("RADAR_DB", str(db.DB_PATH)))
    args = ap.parse_args()

    daily = getattr(config, "DIGEST_FREQUENCY", "weekly") == "daily"
    if args.auto and not daily and dt.datetime.now(dt.timezone.utc).weekday() != 0:
        print("Weekly digest is sent on Mondays; nothing to do today.")
        return
    args.days = args.days or (1 if daily else 7)
    use_resume = getattr(config, "DIGEST_USE_RESUME", False)
    resume = load_resume(ROOT / getattr(config, "RESUME_PATH", "data/resume.pdf")) if use_resume else ""
    if use_resume and not resume:
        print("Note: DIGEST_USE_RESUME is on but no resume was found, so jobs are listed newest first.")
    ranked, stats = build(Path(args.db), args.days, resume)
    stats["label"] = "daily" if args.days == 1 else "weekly"
    if not stats.get("matching"):
        print(f"No new postings matched your filters in the last {args.days} days "
              f"({stats.get('new', 0)} new overall). Nothing to send.")
        return
    top = ranked.head(getattr(config, "DIGEST_TOP_N", 15))
    when = "today" if args.days == 1 else "this week"
    subject = (f"📡 {stats['matching']} new jobs {when} (top match {top.match.max()})" if resume
               else f"📡 {stats['matching']} new jobs {when}")
    html_body, text_body = render_html(top, stats, len(ranked), ranked_by_resume=bool(resume)), render_text(top, stats)
    if args.dry_run:
        out = ROOT / "data" / "digest.html"
        out.write_text(html_body)
        print(f"Dry run: {stats['matching']} postings matched; preview written to {out}\nSubject: {subject}")
    else:
        send(subject, html_body, text_body)


if __name__ == "__main__":
    main()
