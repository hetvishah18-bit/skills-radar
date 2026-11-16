# 📡 Skills Radar

**Track which skills employers are asking for, how that's changing week to week, and where your resume falls short, straight from companies' own career sites, often hours after a job is posted.**

AI is reshaping hiring faster than course catalogs can keep up. Skills Radar collects real job postings from public job-board APIs, pulls out the skills each one mentions, tracks rising and falling skills over time, and scores a resume against current demand.

## What it does

| Tab | What you see |
|---|---|
| **Top skills** | % of postings mentioning each skill, filterable by role and category |
| **Trends** | Week-by-week share for any skills you pick |
| **Rising / falling** | Skills gaining or losing share (last N weeks vs the N before) |
| **Salary by skill** | Median salary of postings mentioning each skill vs. not |
| **2024 vs 2026** | This dataset's top skills per role next to the 2026 benchmark, including the AI-skills jump |
| **My resume gap** | Upload a resume → demand-weighted coverage score + ranked missing skills with trend arrows |
| **Postings** | The underlying jobs, with links, filterable by skill |

## Job-search features
- **🛂 Work-authorization flags:** detects "no sponsorship", "US citizens only / U.S. person (ITAR)" and
  security-clearance requirements (and "sponsorship available"). Toggle *Hide jobs that won't sponsor* in the sidebar.
- **🎓 Early career filter** and **🇺🇸 USA only** filter.
- **🎯 Job match:** your resume vs one posting: score, missing skills, key words, which bullets to lead with.
- **📋 My applications:** save jobs, then track Saved → Applied → Interviewing → Offer/Rejected with dates,
  notes and follow-up reminders. Stored only on your computer in `data/tracker.db`.
- **🕒 Posted within** 24 hours / 3 / 7 / 30 days, using the time each company actually published the job.
- **🏢 Sources:** companies' own career systems: Greenhouse, Lever, Ashby, Workday and SmartRecruiters (plus the
  Remotive remote board).
- **🔎 Company auto-discovery:** every run reads the community-maintained SimplifyJobs New-Grad list, finds
  1,000+ companies' hiring systems, and collects their full job boards automatically (the list only grows).
  Jobs on systems we can't read in full (Apple, TikTok, Microsoft, ...) are added as *title + link*.
  Turn it off with `DISCOVER_COMPANIES = False` in `config.py`.
- **📧 Email digest:** `python digest.py` emails you new early-career US postings, daily (last 24 h) or weekly
  (`--dry-run` to preview). Settings at the bottom of `config.py`.
- **🌐 Online version:** see [DEPLOY.md](DEPLOY.md) for free hosting plus automatic weekly collection with GitHub Actions.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1) Try it instantly with synthetic demo data
python seed_demo.py
RADAR_DB=data/demo.db streamlit run app.py            # Windows PowerShell: $env:RADAR_DB="data/demo.db"; streamlit run app.py

# 2) Collect real postings (run weekly; trends appear after 2+ runs)
python collect.py
streamlit run app.py
```

Edit `config.py` to change target roles, companies (Greenhouse/Lever board slugs) and Remotive searches.

## Real-world data

| Dataset | What it is | How to load |
|---|---|---|
| **LinkedIn Job Postings 2023-24** ([Kaggle: arshkon/linkedin-job-postings](https://www.kaggle.com/datasets/arshkon/linkedin-job-postings)) | 123,849 real US postings with full descriptions, salary, experience level, remote flag. About 6,200 match the default target roles. Mostly posted in April 2024, so it's a **snapshot**. | Download `postings.csv`, then `python import_linkedin.py postings.csv` and `RADAR_DB=data/linkedin.db streamlit run app.py` |
| **Most In-Demand Job Skills of 2026** ([Qarera, CC BY 4.0](https://github.com/dreamjobs-tech/most-in-demand-skills-2026)) | Skill frequencies from 360k postings, Dec 2025 to Jun 2026, by role family and seniority | Already included in `benchmarks/`; powers the **2024 vs 2026** tab |
| **Live job boards** (Greenhouse, Lever, Remotive) | Today's postings | `python collect.py` weekly; builds real trends over time |

**Caveats:** the 2026 benchmark uses a different skill-extraction method, so compare direction and rank, not exact points. Salary-by-skill is confounded by role mix; filter to one role first.

## How it works

```
Greenhouse / Lever / Remotive APIs
        │  collect.py  (filter titles → role buckets, dedupe by job id)
        ▼
  skills.py  (regex taxonomy: ~50 skills in 5 categories)
        ▼
  SQLite: jobs + job_skills   (first_seen date = time axis)
        ▼
  analysis.py (share, weekly trend, movers, resume gap)
        ▼
  app.py (Streamlit + Plotly)
```

**Design choices**
- **Share, not counts.** "% of postings mentioning X" stays comparable even when the number of postings changes week to week.
- **first_seen as the time axis.** A job is counted in the week it first appeared, so a posting left open for months is counted once, in the week it first showed up.
- **Coverage score** = Σ demand share of top-20 skills on your resume ÷ Σ demand share of all top-20 skills.

## Automate weekly collection
- **Mac/Linux cron:** `0 8 * * 1 cd /path/to/skills-radar && .venv/bin/python collect.py`
- **Windows:** Task Scheduler → weekly → `python collect.py`
- **GitHub Actions:** already set up in `.github/workflows/daily.yml` (see DEPLOY.md).

## Roadmap (learning path)
1. ✅ v1: rule-based extraction, trends, resume gap
2. **Evaluate the extractor.** Hand-label 100 postings, measure precision/recall per skill, fix the worst patterns.
3. **LLM extraction.** Send each new posting to an LLM API for structured JSON (skills, seniority, years of experience, salary, visa sponsorship). Compare against the regex baseline from step 2.
4. **Skill co-occurrence graph.** "People who need dbt also need Snowflake" → suggest learning paths.
5. **AI career coach.** RAG over the postings DB: "What should I learn in the next 8 weeks to be a stronger Data Analyst candidate?"
6. **Deploy.** Streamlit Community Cloud + GitHub Actions for weekly collection.

## Notes
- Uses only public, unauthenticated job-board endpoints, called politely (one request every 0.5s). Don't scrape sites that forbid it.
- `seed_demo.py` data is synthetic, and the trends it shows are made up for the demo.
