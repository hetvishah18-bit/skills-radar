"""Import the real-world "LinkedIn Job Postings (2023-2024)" dataset into the radar.

Dataset: ~124k US LinkedIn postings with full descriptions, salary, experience level.
  Kaggle:  https://www.kaggle.com/datasets/arshkon/linkedin-job-postings   (download postings.csv)
  (license: CC BY-SA 4.0 -- see the Kaggle page)

Usage:
    python import_linkedin.py path/to/postings.csv            # -> data/linkedin.db
    RADAR_DB=data/linkedin.db streamlit run app.py

Only postings whose TITLE matches a role in config.TARGET_ROLES are kept.
"""
import sys
import time
from pathlib import Path

import pandas as pd

from radar import db
from radar.collectors import match_role
from radar.skills import extract_skills

OUT = Path(__file__).resolve().parent / "data" / "linkedin.db"
USECOLS = ["job_id", "company_name", "title", "description", "skills_desc", "location",
           "original_listed_time", "listed_time", "formatted_experience_level",
           "remote_allowed", "normalized_salary", "job_posting_url"]


def clean_salary(x):
    # normalized_salary is annualized by the dataset; drop obvious garbage
    return float(x) if pd.notna(x) and 15_000 <= x <= 1_000_000 else None


def main(csv_path: str):
    if OUT.exists():
        OUT.unlink()
    conn = db.connect(OUT)
    t0, seen, kept = time.time(), 0, 0
    for chunk in pd.read_csv(csv_path, usecols=USECOLS, chunksize=10_000):
        seen += len(chunk)
        chunk["role"] = chunk.title.fillna("").map(match_role)
        chunk = chunk[chunk.role.notna()]
        for r in chunk.itertuples(index=False):
            listed = r.original_listed_time if pd.notna(r.original_listed_time) else r.listed_time
            ts = pd.to_datetime(listed, unit="ms", utc=True)
            date = ts.date().isoformat()
            text = f"{r.title} {r.description if isinstance(r.description, str) else ''} " \
                   f"{r.skills_desc if isinstance(r.skills_desc, str) else ''}"
            job = {
                "job_key": f"linkedin:{r.job_id}", "source": "linkedin_kaggle",
                "company": r.company_name if isinstance(r.company_name, str) else None,
                "title": r.title, "role": r.role, "location": r.location,
                "url": r.job_posting_url, "description": r.description if isinstance(r.description, str) else "",
                "first_seen": date,
                "posted_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "seniority": r.formatted_experience_level if isinstance(r.formatted_experience_level, str) else None,
                "remote": 1 if r.remote_allowed == 1 else 0,
                "salary_usd": clean_salary(r.normalized_salary),
            }
            if db.upsert_job(conn, job, extract_skills(text), date):
                kept += 1
        conn.commit()
        print(f"  scanned {seen:>7,} postings, kept {kept:>6,} matching target roles  ({time.time()-t0:.0f}s)")
    print(f"Done -> {OUT}")
    for role, n in conn.execute("SELECT role, COUNT(*) FROM jobs GROUP BY role ORDER BY 2 DESC"):
        print(f"  {role:<22} {n:>6,}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
