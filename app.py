"""Skills Radar dashboard.

    streamlit run app.py                         # real data (data/radar.db)
    RADAR_DB=data/demo.db streamlit run app.py   # synthetic demo data
"""
import io
import os
import re
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from radar import analysis as A
from radar import benchmark as B
from radar import tailor as T
import config
from radar.seniority import LEVELS
from radar import flags as FL
from radar import tracker as TR
from radar import links as LK
from radar.skills import TAXONOMY

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATASET_LABELS = {"radar.db": "Live postings (collected weekly)", "linkedin.db": "LinkedIn snapshot (2024)",
                  "demo.db": "Demo data (synthetic)"}

st.set_page_config(page_title="Skills Radar", page_icon="📡", layout="wide")

# On a public deployment, personal features (tracker, saving) are hidden: set RADAR_PUBLIC=1
PUBLIC = os.environ.get("RADAR_PUBLIC") == "1"


@st.cache_data(ttl=300)
def load_data(db_path: str):
    with sqlite3.connect(db_path) as conn:
        return A.load(conn)


# Online version: download the latest job database from the GitHub release (refreshed every 6 hours)
def _fetch_remote_db():
    import gzip, shutil, time, urllib.request
    url = os.environ.get("RADAR_DATA_URL")
    target = DATA_DIR / "radar.db"
    if not url or (target.exists() and time.time() - target.stat().st_mtime < 6 * 3600):
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_DIR / "radar.db.download"
    try:
        with st.spinner("Downloading the latest job data…"):
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            if url.endswith(".gz"):
                with gzip.open(tmp) as src, open(str(tmp) + ".db", "wb") as dst:
                    shutil.copyfileobj(src, dst)
                tmp.unlink()
                tmp = Path(str(tmp) + ".db")
            tmp.replace(target)
            st.cache_data.clear()
    except Exception as e:
        if not target.exists():
            st.error(f"Couldn't download the job data from {url}: {e}")


_fetch_remote_db()

# Pick the dataset: RADAR_DB wins; otherwise a sidebar switcher over the .db files in data/
if os.environ.get("RADAR_DB"):
    DB = Path(os.environ["RADAR_DB"])
else:
    _dbs = sorted((p for p in DATA_DIR.glob("*.db") if p.name != "tracker.db"),
                  key=lambda p: list(DATASET_LABELS).index(p.name) if p.name in DATASET_LABELS else 99)
    if len(_dbs) > 1:
        DB = st.sidebar.selectbox("Dataset", _dbs, format_func=lambda p: DATASET_LABELS.get(p.name, p.stem))
    else:
        DB = _dbs[0] if _dbs else DATA_DIR / "radar.db"

if not DB.exists():
    st.title("📡 Skills Radar")
    st.warning(f"No database at `{DB}`. Run `python collect.py` (real data) "
               "or `python seed_demo.py` and set `RADAR_DB=data/demo.db` (demo data).")
    st.stop()

jobs, skills = load_data(str(DB))
if jobs.empty:
    st.warning("Database is empty. Run `python collect.py` first.")
    st.stop()

# ---- sidebar filters ---------------------------------------------------------
st.sidebar.title("📡 Skills Radar")
if "demo" in DB.name:
    st.sidebar.info("Showing **synthetic demo data**. Trends are made up.")
elif "linkedin" in DB.name:
    st.sidebar.info("**Real data:** LinkedIn Job Postings 2023-24 (Kaggle, arshkon). "
                    "Mostly posted in April 2024, so it's a snapshot, not a trend.")
roles = sorted(jobs.role.dropna().unique())
pick_roles = st.sidebar.multiselect("Roles", roles, default=roles)
cats = list(TAXONOMY)
pick_cats = st.sidebar.multiselect("Skill categories", cats, default=cats)
early_only = st.sidebar.toggle("🎓 Early career only", value=False,
                               help="New grad / entry / junior / 'Engineer I' titles, or postings asking for 0-2 years "
                                    "of experience. Internships excluded.")
levels = [l for l in LEVELS if l in set(jobs.level)]
pick_levels = ["Early career"] if early_only else st.sidebar.multiselect("Career level", levels, default=levels)
hide_blocked = st.sidebar.toggle(
    "🛂 Hide jobs that won't sponsor", value=False,
    help="Hides postings that say they won't sponsor visas, require US citizenship / 'U.S. person' status, "
         "or need a security clearance. Useful for international students (F-1, OPT, STEM OPT). "
         "Postings that don't mention it stay visible, so always confirm with the employer.")
WITHIN = {"Any time": None, "Last 24 hours": 24, "Last 3 days": 72, "Last 7 days": 168, "Last 30 days": 720}
within = st.sidebar.selectbox("🕒 Posted within", list(WITHIN),
                              help="When the company published the job on its own careers site. "
                                   "Collect daily (python collect.py) so new jobs show up within a day.")
open_only = st.sidebar.checkbox("✅ Open jobs only", value=True,
                                help="Hides jobs the company has taken down since they were collected. "
                                     "This updates every time you run python collect.py.")
us_only = st.sidebar.checkbox("🇺🇸 USA only", value=True,
                              help="Keep only jobs located in the US (including 'Remote - US').")
remote_only = st.sidebar.checkbox("Remote only")

f_jobs = jobs[jobs.role.isin(pick_roles)]
if open_only:
    f_jobs = f_jobs[f_jobs.is_open]
if us_only:
    f_jobs = f_jobs[f_jobs.is_us]
if hide_blocked:
    f_jobs = f_jobs[~f_jobs.auth_blocked]
if WITHIN[within]:
    f_jobs = f_jobs[A.posted_within(f_jobs, WITHIN[within])]
    if f_jobs.empty:
        st.info(f"No postings from the {within.lower()} with these filters. Run `python collect.py` to fetch the "
                "newest jobs" + (" (this dataset is an old snapshot)." if "linkedin" in DB.name else "."))
        st.stop()
f_jobs = f_jobs[f_jobs.level.isin(pick_levels)]
if remote_only:
    f_jobs = f_jobs[(f_jobs.remote == 1) | f_jobs.location.str.contains("remote", case=False, na=False)]
f_skills = skills[skills.job_key.isin(f_jobs.job_key) & skills.category.isin(pick_cats)]

st.title("Which skills is the job market asking for?")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Postings", f"{len(f_jobs):,}",
          help=f"{(jobs.level == 'Early career').sum():,} of all postings are early career")
c2.metric("Companies", f_jobs.company.nunique())
c3.metric("Weeks of data", f_jobs.week.nunique())
c4.metric("Skills tracked", f_skills.skill.nunique())

_TABS = {"Top skills": "top", "Trends": "trend", "Rising / falling": "move", "Salary by skill": "pay",
         "2024 vs 2026": "bench", "My resume gap": "resume", "🎯 Job match": "tailor", "Postings": "jobs",
         "📋 My applications": "apps"}
_hidden = set(getattr(config, "HIDDEN_TABS", [])) | ({"📋 My applications"} if PUBLIC else set())
_shown = [n for n in _TABS if n not in _hidden]
_made = dict(zip(_shown, st.tabs(_shown)))
_T = {v: _made.get(n) for n, v in _TABS.items()}
tab_top, tab_trend, tab_move, tab_pay, tab_bench = _T["top"], _T["trend"], _T["move"], _T["pay"], _T["bench"]
tab_resume, tab_tailor, tab_jobs, tab_apps = _T["resume"], _T["tailor"], _T["jobs"], _T["apps"]

# ---- top skills --------------------------------------------------------------
if tab_top is not None:
    with tab_top:
        share = A.skill_share(f_jobs, f_skills).head(25)
        fig = px.bar(share.iloc[::-1], x="share", y="skill", color="category", orientation="h",
                     labels={"share": "% of postings mentioning skill", "skill": ""},
                     hover_data={"postings": True, "share": ":.1%"})
        fig.update_layout(xaxis_tickformat=".0%", height=650, legend_title_text="",
                          yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")

        st.subheader("Top skills by role")
        rows = []
        for r in pick_roles:
            rj = f_jobs[f_jobs.role == r]
            top = A.skill_share(rj, f_skills[f_skills.job_key.isin(rj.job_key)]).head(8)
            rows.append({"Role": r, "Postings": len(rj),
                         "Top skills": " · ".join(f"{s} {v:.0%}" for s, v in zip(top.skill, top.share))})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ---- trends ------------------------------------------------------------------
if tab_trend is not None:
    with tab_trend:
        solid_weeks = int((f_jobs.groupby("week").size() >= 50).sum())
        if solid_weeks < 6:
            st.info(f"Only {solid_weeks} week(s) with 50+ postings here, too few for a real trend. "
                    "Run `collect.py` weekly to build history, or see the **2024 vs 2026** tab.")
        wk = A.weekly_share(f_jobs, f_skills)
        default = A.skill_share(f_jobs, f_skills).skill.head(5).tolist()
        pick = st.multiselect("Skills to plot", sorted(wk.skill.unique()), default=default)
        if pick:
            fig = px.line(wk[wk.skill.isin(pick)], x="week", y="share", color="skill", markers=True,
                          labels={"share": "% of that week's postings", "week": "Week"},
                          hover_data={"n": True, "n_jobs": True})
            fig.update_layout(yaxis_tickformat=".0%", legend_title_text="")
            st.plotly_chart(fig, width="stretch")
        st.caption("Small weeks are noisy. Trust a trend once you have a few hundred postings per week.")

# ---- movers ------------------------------------------------------------------
if tab_move is not None:
    with tab_move:
        win = st.slider("Compare the last N weeks vs the N weeks before", 1, 8, 4)
        mv = A.movers(f_jobs, f_skills, window_weeks=win)
        if mv.empty:
            st.info("Need at least 2 weeks of data.")
        else:
            mv = mv[mv.change_pts.abs() >= 0.5]
            fig = px.bar(mv.sort_values("change_pts"), x="change_pts", y="skill", orientation="h",
                         color=mv.sort_values("change_pts").change_pts > 0,
                         color_discrete_map={True: "#2a9d8f", False: "#e76f51"},
                         labels={"change_pts": "Change in share (percentage points)", "skill": ""})
            fig.update_layout(showlegend=False, height=max(350, 22 * len(mv)))
            st.plotly_chart(fig, width="stretch")
            show = mv.assign(before=mv.before.map("{:.1%}".format), now=mv.now.map("{:.1%}".format),
                             change_pts=mv.change_pts.round(1))
            st.dataframe(show[["skill", "category", "before", "now", "change_pts", "postings_now"]],
                         hide_index=True, width="stretch")


# ---- salary ------------------------------------------------------------------
if tab_pay is not None:
    with tab_pay:
        pay = A.salary_by_skill(f_jobs, f_skills)
        n_paid = int(f_jobs.salary_usd.notna().sum())
        if pay.empty:
            st.info("No salary data in this dataset/selection (needs at least 25 salaried postings per skill).")
        else:
            st.caption(f"Based on {n_paid:,} postings that list a salary (annualized). "
                       "Pick ONE role in the sidebar for a fair comparison; otherwise role mix drives the gaps "
                       "(e.g. engineering skills look 'premium' because engineers earn more than PMs).")
            top = pay.head(20).iloc[::-1]
            fig = px.bar(top, x="with_skill", y="skill", orientation="h", color="category",
                         hover_data={"without_skill": ":$,.0f", "premium": ":+.0%", "n": True},
                         labels={"with_skill": "Median salary of postings mentioning the skill", "skill": ""})
            fig.update_layout(xaxis_tickformat="$,.0f", height=600, legend_title_text="")
            st.plotly_chart(fig, width="stretch")
            st.dataframe(pay.assign(with_skill=pay.with_skill.map("${:,.0f}".format),
                                    without_skill=pay.without_skill.map("${:,.0f}".format),
                                    premium=pay.premium.map("{:+.0%}".format)),
                         hide_index=True, width="stretch")

# ---- 2024 vs 2026 benchmark --------------------------------------------------
if tab_bench is not None:
    with tab_bench:
        if not B.available():
            st.info("Benchmark files not found in `benchmarks/`.")
        else:
            st.markdown("Compares this dataset with **Qarera's Most In-Demand Job Skills of 2026** "
                        "(360k postings, Dec 2025 to Jun 2026, CC BY 4.0). The two use different skill "
                        "extraction methods, so read **direction and rank**, not exact percentage points.")
            roles_b = [r for r in pick_roles if r in B.ROLE_MAP]
            if not roles_b:
                st.warning("Pick a role that has a 2026 benchmark: " + ", ".join(B.ROLE_MAP))
            else:
                role = st.selectbox("Role", roles_b)
                rj = f_jobs[f_jobs.role == role]
                ours = A.skill_share(rj, skills[skills.job_key.isin(rj.job_key)]).set_index("skill").share
                bench = B.by_role()
                bench = bench[bench.role_family == B.ROLE_MAP[role]]
                left, right = st.columns(2)
                left.markdown(f"**This dataset**: top skills, {role} ({len(rj):,} postings)")
                left.dataframe(ours.head(15).map("{:.0%}".format).rename("share").reset_index(),
                               hide_index=True, width="stretch")
                right.markdown(f"**2026 benchmark**: {B.ROLE_MAP[role]} "
                               f"({int(bench.role_postings.iloc[0]):,} postings)")
                right.dataframe(bench[["skill", "share"]].head(15).assign(share=lambda d: d.share.map("{:.0%}".format)),
                                hide_index=True, width="stretch")
                b = bench.assign(canon=bench.skill.map(B.SKILL_MAP)).dropna(subset=["canon"])
                cmp = pd.DataFrame({"then": ours, "now": b.set_index("canon").share}).dropna()
                if not cmp.empty:
                    cmp = cmp.reset_index(names="skill").melt("skill", var_name="period", value_name="share")
                    cmp["period"] = cmp.period.map({"then": "This dataset", "now": "2026 benchmark"})
                    fig = px.bar(cmp, x="share", y="skill", color="period", barmode="group", orientation="h",
                                 labels={"share": "% of postings", "skill": ""})
                    fig.update_layout(xaxis_tickformat=".0%", height=max(350, 45 * cmp.skill.nunique()),
                                      legend_title_text="", yaxis={"categoryorder": "total ascending"})
                    st.plotly_chart(fig, width="stretch")
                ai = bench[bench.skill.isin(["ai", "llm", "llms", "generative ai", "genai", "machine learning"])]
                if not ai.empty:
                    st.markdown("**AI skills in 2026 for this role:** " +
                                ", ".join(f"`{r.skill}` {r.share:.0%}" for r in ai.itertuples()) +
                                f" vs. **LLMs / GenAI {ours.get('LLMs / GenAI', 0):.1%}** in this dataset.")
            with st.expander("2026: share of postings asking for AI skills, by seniority"):
                sen = B.ai_by_seniority()
                st.plotly_chart(px.bar(sen, x="seniority", y="ai_pct_of_level",
                                       labels={"ai_pct_of_level": "% of postings requesting AI", "seniority": ""}),
                                width="stretch")

# ---- resume gap --------------------------------------------------------------
def read_resume(file) -> str:
    name = file.name.lower()
    data = file.getvalue()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        import docx  # pip install python-docx
        return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
    return data.decode("utf-8", errors="ignore")


if tab_resume is not None:
    with tab_resume:
        st.write("Upload your resume (PDF, DOCX or TXT) or paste it. Nothing leaves your computer.")
        up = st.file_uploader("Resume", type=["pdf", "docx", "txt"])
        pasted = st.text_area("…or paste resume text", height=120)
        text = read_resume(up) if up else pasted
        if text.strip():
            st.session_state["resume_text"] = text   # shared with the Tailor tab
        target = st.selectbox("Compare against", ["All selected roles"] + pick_roles)
        if text.strip():
            tj = f_jobs if target == "All selected roles" else f_jobs[f_jobs.role == target]
            have, gap = A.resume_gap(text, tj, f_skills[f_skills.job_key.isin(tj.job_key)], top_n=20)
            score = A.coverage_score(gap)
            m1, m2 = st.columns([1, 3])
            m1.metric("Market coverage", f"{score:.0f}%",
                      help="Demand-weighted share of the top 20 skills that appear on your resume")
            m2.write("**Skills found on your resume:** " + (", ".join(sorted(have)) or "none detected"))

            missing = gap[~gap.on_resume]
            st.subheader("Biggest gaps (ranked by demand)")
            if missing.empty:
                st.success("Your resume covers all of the top 20 skills for this selection.")
            else:
                mv_all = A.movers(tj, f_skills[f_skills.job_key.isin(tj.job_key)]).set_index("skill")
                missing = missing.assign(
                    demand=missing.share.map("{:.0%}".format),
                    trend=missing.skill.map(lambda s: mv_all.change_pts.get(s, 0)).map(
                        lambda x: f"▲ {x:+.1f} pts" if x > 0.5 else (f"▼ {x:+.1f} pts" if x < -0.5 else "—")))
                st.dataframe(missing[["skill", "category", "demand", "trend"]],
                             hide_index=True, width="stretch")
                st.caption("Tip: a gap that is both high-demand and rising (▲) is the best thing to learn next. "
                           "If you already have the skill, make sure the resume says it in words employers use.")


# ---- tailor resume -----------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_idf(db_path: str):
    with sqlite3.connect(db_path) as conn:
        return T.build_idf(d for (d,) in conn.execute("SELECT description FROM jobs"))


@st.cache_data(show_spinner=False)
def load_posting(db_path: str, job_key: str):
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT title, company, description, url FROM jobs WHERE job_key = ?",
                            (job_key,)).fetchone()


def chips(items, color):
    return " ".join(f":{color}-background[{i}]" for i in sorted(items)) or "—"


if tab_tailor is not None:
    with tab_tailor:
        st.write("Pick a posting (or paste any job description), add your resume, and see how well it matches: "
                 "which of the job's skills and words you already show, what's missing, and which bullets to lead with.")
        left, right = st.columns(2)
        with left:
            st.markdown("**1. The job**")
            src = st.radio("Job source", ["Pick from the radar", "Paste a job description"],
                           horizontal=True, label_visibility="collapsed")
            jd = job_title = company = url = ""
            key = None
            if src == "Pick from the radar":
                pool = f_jobs.sort_values("posted_ts", ascending=False).head(2000)
                labels = {k: f"{t} · {c} · {l or ''}" for k, t, c, l in
                          zip(pool.job_key, pool.title, pool.company, pool.location)}
                key = st.selectbox(f"Posting ({len(pool):,} match your sidebar filters, type to search)",
                                   list(labels), format_func=labels.get, index=None,
                                   placeholder="Type a title or company…")
                if key:
                    job_title, company, jd, url = load_posting(str(DB), key)
                    if url:
                        _bk = LK.backup_url(key) if not LK.is_greenhouse_hosted(url) else None
                        st.markdown(f"[Open the original posting ↗]({url})"
                                    + (f" · [Backup: Greenhouse copy ↗]({_bk})" if _bk else ""))
                    if len(T.clean_text(jd or "")) < 200:
                        st.info("The radar only has this job's title and link (the company uses a careers system "
                                "the radar can't read in full). Open the posting, copy the description, and use "
                                "**Paste a job description** above to check your match.")
                        jd = ""
                    for fl in FL.work_auth_flags(jd):
                        ev = FL.evidence(jd, fl, 70)
                        (st.success if fl == FL.SPONSORS else st.warning)(f"**{fl}**: “{ev}”")
                    with st.expander("Read the job description"):
                        st.write(T.clean_text(jd)[:6000])
            else:
                job_title = st.text_input("Job title (optional)")
                company = st.text_input("Company (optional)")
                jd = st.text_area("Paste the job description", height=220)
        with right:
            st.markdown("**2. Your resume**")
            up_t = st.file_uploader("Resume (PDF, DOCX or TXT)", type=["pdf", "docx", "txt"], key="tailor_up")
            if up_t is not None:
                fid = (up_t.name, up_t.size)
                if st.session_state.get("tailor_file_id") != fid:      # new upload -> load its text into the box
                    st.session_state["tailor_resume"] = read_resume(up_t)
                    st.session_state["tailor_file_id"] = fid
            elif "tailor_resume" not in st.session_state:
                st.session_state["tailor_resume"] = st.session_state.get("resume_text", "")
            resume = st.text_area("Resume text (edit here if the PDF came out messy)", height=220,
                                  key="tailor_resume")
            if up_t is not None and not resume.strip():
                st.warning("Couldn't read any text from this file (it may be a scanned image). "
                           "Paste your resume text into the box above instead.")

        if not (jd and jd.strip() and resume.strip()):
            st.info("Add a job and your resume to see the match check.")
        else:
            rep = T.match(resume, jd, idf=load_idf(str(DB)))
            st.divider()
            st.subheader("Match check")
            if not PUBLIC and st.button("📌 Save this job to My applications"):
                row = f_jobs[f_jobs.job_key == key].iloc[0] if src == "Pick from the radar" and key else None
                added = TR.add({"job_key": key if row is not None else None, "title": job_title or "Pasted job",
                                "company": company, "url": url, "location": None if row is None else row.location,
                                "match_score": round(rep.score), "work_auth": ", ".join(FL.work_auth_flags(jd))})
                st.toast("Saved to My applications 📋" if added else "Already in My applications")
            m1, m2, m3 = st.columns(3)
            m1.metric("Match score", f"{rep.score:.0f}/100",
                      help="70% = share of the job's skills found on your resume, 30% = share of the job's "
                           "most distinctive repeated words found on your resume. Postings that name only a few "
                           "skills are pulled toward 50, so vague postings can't score 100.")
            m2.metric("Job skills you show", f"{len(rep.have)}/{len(rep.jd_skills)}")
            m3.metric("Key words you use", f"{len(rep.keywords) - len(rep.keywords_missing)}/{len(rep.keywords)}")
            st.markdown("**Skills the job asks for:** ✅ " + chips(rep.have, "green") +
                        "  \n❌ " + chips(rep.missing, "red"))
            st.markdown("**Words this posting repeats:** " + " ".join(
                f":{'green' if k not in rep.keywords_missing else 'gray'}-background[{k}]" for k in rep.keywords))
            st.caption("Green = already on your resume. Only add a missing skill or word if it is true for you; "
                       "if you have it, say it the way the posting does.")
            if rep.top_bullets:
                st.markdown("**Lead with these bullets** (they hit the most of this job's needs):")
                for b, n, hits in rep.top_bullets[:5]:
                    st.markdown(f"- {b}  \n  <small>matches: {', '.join(hits)}</small>", unsafe_allow_html=True)

        if jd and jd.strip() and resume.strip() and getattr(config, "SHOW_AI_TAILORING", False):
            st.divider()
            st.subheader("✨ AI tailoring")
            key_env = os.environ.get("ANTHROPIC_API_KEY", "")
            api_key = key_env or st.text_input(
                "Anthropic API key", type="password",
                help="Get one at console.anthropic.com. Or set the ANTHROPIC_API_KEY environment variable "
                     "before starting the app so you don't have to paste it.")
            st.caption("Sends this job description and your resume to Anthropic's API. Usually costs a few cents. "
                       "The AI may reorder, reword and trim, but is told never to add skills, numbers or "
                       "experience you don't have, and the result is double-checked below.")
            run_key = f"tailored::{hash((resume, jd))}"
            if st.button("✨ Tailor my resume for this job", type="primary", disabled=not api_key):
                with st.spinner("Tailoring… (about 20-40 seconds)"):
                    try:
                        st.session_state[run_key] = T.ai_tailor(resume, jd, job_title, company, api_key=api_key)
                    except Exception as e:
                        st.error(f"Tailoring failed: {e.__class__.__name__}: {e}")
            out = st.session_state.get(run_key)
            if out:
                md = out.get("tailored_resume_markdown", "")
                after = T.match(md, jd, idf=load_idf(str(DB)))
                a1, a2 = st.columns(2)
                a1.metric("Match score after tailoring", f"{after.score:.0f}/100", f"{after.score - rep.score:+.0f}")
                a2.metric("Job skills shown", f"{len(after.have)}/{len(after.jd_skills)}",
                          f"{len(after.have) - len(rep.have):+d}")
                flags = out.get("honesty_flags", {})
                if flags.get("new_skills") or flags.get("new_numbers"):
                    st.warning("**Check these before you send it.** They appear in the tailored version but not in "
                               "your original resume:  \n"
                               + (f"Skills: **{', '.join(flags['new_skills'])}**  \n" if flags.get("new_skills") else "")
                               + (f"Numbers: **{', '.join(flags['new_numbers'])}**  \n" if flags.get("new_numbers") else "")
                               + "Keep them only if they're true; otherwise delete them in the editor below.")
                else:
                    st.success("Honesty check passed: no new skills or numbers were added.")

                t1, t2, t3 = st.tabs(["Tailored resume", "What changed", "Gaps to address"])
                with t1:
                    edited = st.text_area("Edit before downloading (Markdown)", md, height=420, key=f"edit::{run_key}")
                    fname = re.sub(r"[^A-Za-z0-9]+", "_", f"Resume_{company}_{job_title}".strip("_"))[:60] or "Resume"
                    d1, d2 = st.columns(2)
                    d1.download_button("⬇ Download Word (.docx)", T.markdown_to_docx(edited), f"{fname}.docx",
                                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                    d2.download_button("⬇ Download Markdown", edited, f"{fname}.md", "text/markdown")
                    with st.expander("Preview"):
                        st.markdown(edited)
                with t2:
                    ch = pd.DataFrame(out.get("changes", []))
                    if ch.empty:
                        st.write("No line-level changes reported.")
                    else:
                        st.dataframe(ch.rename(columns=str.title), hide_index=True, width="stretch")
                with t3:
                    gaps = out.get("gaps", [])
                    if not gaps:
                        st.write("No gaps reported.")
                    for g in gaps:
                        st.markdown(f"- **{g.get('requirement', '')}**: {g.get('suggestion', '')}")

# ---- raw postings ------------------------------------------------------------
if tab_jobs is not None:
    with tab_jobs:
        skill_filter = st.selectbox("Postings that mention…", ["(any)"] + sorted(f_skills.skill.unique()))
        view = f_jobs
        if skill_filter != "(any)":
            view = view[view.job_key.isin(f_skills[f_skills.skill == skill_filter].job_key)]
        view = view.sort_values("posted_ts", ascending=False).reset_index(drop=True)
        _now = pd.Timestamp.now(tz="UTC")
        view["posted"] = [A.posted_label(t, e, _now) for t, e in zip(view.posted_ts, view.posted_exact)]
        if not PUBLIC:
            st.caption("Tick rows on the left, then save them to **📋 My applications**.")
        view["details"] = view.source.map(lambda x: "title + link" if x == "list" else "full")
        view["backup"] = [LK.backup_url(k) if not LK.is_greenhouse_hosted(u) else None
                          for k, u in zip(view.job_key, view.url)]
        sel = st.dataframe(view[["posted", "role", "level", "min_years", "work_auth", "title", "company",
                                 "location", "details", "url", "backup"]],
                           hide_index=True, width="stretch",
                           on_select="ignore" if PUBLIC else "rerun", selection_mode="multi-row", key="postings_table",
                           column_config={"url": st.column_config.LinkColumn("Link"),
                                          "backup": st.column_config.LinkColumn(
                                              "Backup link", display_text="Greenhouse copy",
                                              help="If the company's link shows 404, try this: Greenhouse's own copy "
                                                   "of the posting. If this one also fails, the job was closed."),
                                          "posted": "Posted",
                                          "details": st.column_config.TextColumn(
                                              "Details", help="full = description, skills and flags available; "
                                                              "title + link = open the link for the description"),
                                          "level": "Career level", "role": "Role", "title": "Job title",
                                          "company": "Company", "location": "Location",
                                          "work_auth": "Work authorization",
                                          "min_years": st.column_config.NumberColumn("Min yrs asked", format="%d")})
        rows = [] if PUBLIC else sel.selection.rows
        if rows and st.button(f"📌 Save {len(rows)} selected to My applications"):
            n = sum(TR.add({"job_key": r.job_key, "title": r.title, "company": r.company, "location": r.location,
                            "url": r.url, "work_auth": r.work_auth}) for r in view.iloc[rows].itertuples())
            st.toast(f"Saved {n} new job(s) 📋" + (f" ({len(rows) - n} already saved)" if n < len(rows) else ""))

# ---- my applications ---------------------------------------------------------
if tab_apps is not None:
    with tab_apps:
        apps = TR.load()
        if apps.empty:
            st.info("No saved jobs yet. Save jobs from **🎯 Job match** or **Postings**, or add one by hand "
                    "in the table below (click the + under the table).")
        counts = apps.status.value_counts()
        cols = st.columns(len(TR.STATUSES))
        for c, stt in zip(cols, TR.STATUSES):
            c.metric(stt, int(counts.get(stt, 0)))

        due = TR.due_followups(apps)
        if not due.empty:
            st.warning("**Follow-ups due:** " + "; ".join(
                f"{r.title} at {r.company or '?'} (applied {r.date_applied})" for r in due.itertuples()) +
                ". A short, polite check-in email to the recruiter works well. Then push the date forward.")

        st.caption("Edit right in the table: change **Status**, dates and notes, add rows with + or delete "
                   "rows, then click **Save changes**. Moving a job to *Applied* fills in today's date and "
                   f"a follow-up {TR.FOLLOW_UP_DAYS} days later.")
        # The key changes whenever the saved data changes, so half-finished edits from before can never
        # be applied to the wrong rows after a job is saved from another tab.
        edited = st.data_editor(
            apps, key=f"apps_editor_{TR.version()}", num_rows="dynamic", hide_index=True, width="stretch",
            column_order=["status", "title", "company", "location", "date_saved", "date_applied", "follow_up",
                          "match_score", "work_auth", "notes", "url"],
            column_config={
                "status": st.column_config.SelectboxColumn("Status", options=TR.STATUSES, required=True,
                                                           default="Saved"),
                "title": st.column_config.TextColumn("Job title", required=True),
                "company": "Company", "location": "Location",
                "date_saved": st.column_config.DateColumn("Saved", disabled=True),
                "date_applied": st.column_config.DateColumn("Applied"),
                "follow_up": st.column_config.DateColumn("Follow up"),
                "match_score": st.column_config.NumberColumn("Match", format="%d", disabled=True),
                "work_auth": st.column_config.TextColumn("Work auth.", disabled=True),
                "notes": st.column_config.TextColumn("Notes", width="large"),
                "url": st.column_config.LinkColumn("Link"),
            })
        gone = TR.to_delete(edited)
        confirm = True
        if not gone.empty:
            st.warning(f"**Saving will delete {len(gone)} job(s):** "
                       + "; ".join(f"{r.title} at {r.company or '?'}" for r in gone.itertuples()))
            confirm = st.checkbox(f"Yes, delete {'it' if len(gone) == 1 else 'them'}", value=False,
                                  key=f"confirm_del_{TR.version()}")
        b1, b2 = st.columns([1, 4])
        if b1.button("💾 Save changes", type="primary"):
            n = TR.save(edited, allow_delete=confirm and not gone.empty)
            st.toast("Saved ✔" + (f" ({n} deleted)" if n else "")
                     + (" (deleted rows were kept: tick the box to delete)" if not gone.empty and not confirm else ""))
            st.rerun()
        if not apps.empty:
            b2.download_button("⬇ Export to CSV", apps.to_csv(index=False), "my_applications.csv", "text/csv")

        backups = TR.list_backups()
        if backups:
            with st.expander(f"↩ Restore from a backup ({len(backups)} saved automatically)"):
                st.caption("A backup is saved before every change. Restoring adds back any job from that backup "
                           "that's missing now. It never overwrites or deletes anything.")
                pick = st.selectbox("Backup", backups, format_func=lambda p: p.stem.replace("tracker-", "")[:15]
                                    .replace("-", " at ", 1))
                if st.button("Restore missing jobs from this backup"):
                    n = TR.restore(pick)
                    st.toast(f"Restored {n} job(s)" if n else "Nothing missing: all jobs in that backup are already here")
                    st.rerun()
