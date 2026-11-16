"""Resume tailoring.

Part 1 (free, no API): compare a resume to a job description -> keyword coverage, missing skills,
                        which existing bullets to lead with.
Part 2 (AI, needs ANTHROPIC_API_KEY): rewrite the resume for the posting WITHOUT inventing anything,
                        then double-check the output for skills that weren't in the original.
Part 3: export the tailored resume (markdown) to a .docx file.
"""
from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass, field

from radar.skills import clean_text, extract_skills

# --------------------------------------------------------------------------- #
# Part 1: free match check
# --------------------------------------------------------------------------- #
_STOP = set("""a an and are as at be by for from has have in is it its of on or our that the this to we
will with you your their they them who what when where which while about across into over under
using use used work working team teams role job company experience years year ability strong
including include etc such other more most all any can may must should would could also well new
identify participate related skills standard responsibilities requirements required preferred
qualifications qualification knowledge support ensure provide perform performs duties duty position
candidate candidates opportunity environment excellent plus ideal ideally within based level levels
able related relevant various multiple other others help helps make makes need needs including e.g
i.e understanding understand day days time per one two three us our we're you'll who's employer
equal applicants status law benefits salary pay range location hybrid remote office
through both ready part bring like get set best great good high highly key across data
least minimum preferably must-have nice-to-have""".split())
_BULLET = re.compile(r"^\s*(?:[-•▪●◦*–]|\d+[.)])\s+")


def _words(text: str) -> list[str]:
    text = re.sub(r"(?<=[a-z])\.(?=[A-Za-z]{2})", ". ", text)   # "process.Analyze" -> two words
    toks = (w.strip(".-/") for w in re.findall(r"[a-z][a-z0-9+#./-]{1,}", text.lower()))
    return [w for w in toks if len(w) > 2 and w not in _STOP]


def build_idf(descriptions) -> dict[str, float]:
    """Inverse document frequency from a pile of job descriptions (words common everywhere score low)."""
    import math
    df: dict[str, int] = {}
    n = 0
    for d in descriptions:
        n += 1
        for w in set(_words(clean_text(d or ""))):
            df[w] = df.get(w, 0) + 1
    return {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()} if n else {}


def jd_keywords(jd: str, top_n: int = 20, idf: dict[str, float] | None = None) -> list[str]:
    """Words this JD repeats that are NOT generic across all postings (TF-IDF when idf is given)."""
    words = _words(jd)
    tf: dict[str, int] = {}
    for w in words:
        tf[w] = tf.get(w, 0) + 1
    default = max(idf.values()) if idf else 1.0
    score = {w: c * (idf.get(w, default) if idf else 1.0) for w, c in tf.items() if c >= 2}
    return sorted(score, key=lambda w: -score[w])[:top_n]


def resume_bullets(resume: str) -> list[str]:
    lines = [l.strip() for l in resume.splitlines()]
    bullets = [_BULLET.sub("", l) for l in lines if _BULLET.match(l)]
    if len(bullets) < 3:  # PDF text often loses bullet characters: fall back to sentence-ish lines
        bullets = [l for l in lines if len(l.split()) >= 6]
    return bullets


@dataclass
class MatchReport:
    score: float                       # 0-100
    jd_skills: set[str]
    have: set[str]
    missing: set[str]
    keywords: list[str]
    keywords_missing: list[str]
    top_bullets: list[tuple[str, int, list[str]]] = field(default_factory=list)  # (bullet, hits, matched)


def match(resume: str, jd: str, idf: dict[str, float] | None = None) -> MatchReport:
    jd = clean_text(jd)
    jd_sk, cv_sk = extract_skills(jd), extract_skills(resume)
    from radar.skills import TAXONOMY
    skill_words = {w.lower() for cat in TAXONOMY.values() for sk in cat for w in re.split(r"[ /]+", sk)}
    kws = [k for k in jd_keywords(jd, top_n=30, idf=idf) if k not in skill_words][:20]
    low = resume.lower()
    kw_missing = [k for k in kws if k not in low]
    # score: 70% taxonomy skills, 30% other repeated JD keywords.
    # Shrink toward 50% when a posting names few skills/keywords, so vague postings can't score 100.
    sk_part = (len(jd_sk & cv_sk) + 0.5 * 2) / (len(jd_sk) + 2)
    kw_part = (len(kws) - len(kw_missing) + 0.5 * 3) / (len(kws) + 3)
    score = 100 * (0.7 * sk_part + 0.3 * kw_part)

    ranked = []
    for b in resume_bullets(resume):
        bl = b.lower()
        hits = sorted({s for s in extract_skills(b) if s in jd_sk} | {k for k in kws if k in bl}, key=str.lower)
        if hits:
            ranked.append((b, len(hits), hits))
    ranked.sort(key=lambda x: -x[1])
    return MatchReport(score, jd_sk, jd_sk & cv_sk, jd_sk - cv_sk, kws, kw_missing, ranked[:8])


# --------------------------------------------------------------------------- #
# Part 2: AI tailoring
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """You are an expert technical recruiter and resume editor. You tailor a candidate's
resume to one specific job posting.

HARD RULES (never break these):
1. Never invent anything. No new employers, titles, dates, degrees, certifications, tools, skills,
   metrics or numbers that are not in the original resume. Do not inflate scope or seniority.
2. You MAY: reorder sections and bullets, rewrite bullets to use the job's vocabulary when it describes
   the SAME work, merge or trim weak bullets, tighten wording, write a short summary built only from
   facts in the resume, and reorder the skills list to put the job's skills first.
3. If the job asks for something the resume does not show, do NOT add it. List it under "gaps" with an
   honest suggestion (e.g. a real project to mention in a cover letter, or something to learn).
4. Keep the candidate's real voice and keep it to roughly the same length (one page if it was one page).
5. Use plain US English, strong action verbs, no buzzword stuffing, no first person.

Return ONLY a JSON object, no prose, with exactly these keys:
{
  "tailored_resume_markdown": "the full tailored resume in Markdown: '# Name' line, contact line, '## Section' headings, '- ' bullets, '### Role | Company | Dates' for jobs",
  "changes": [{"original": "original bullet or line", "tailored": "new version", "why": "short reason tied to the job"}],
  "gaps": [{"requirement": "what the job asks for", "suggestion": "honest way to address it"}],
  "keywords_used": ["job keywords that now appear in the resume, all backed by original content"]
}"""


def build_user_prompt(resume: str, jd: str, job_title: str = "", company: str = "") -> str:
    head = f"JOB: {job_title} at {company}\n" if job_title or company else ""
    return (f"{head}<job_description>\n{clean_text(jd)[:15000]}\n</job_description>\n\n"
            f"<original_resume>\n{resume[:15000]}\n</original_resume>\n\n"
            "Tailor the resume for this job following the hard rules. Return only the JSON object.")


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def ai_tailor(resume: str, jd: str, job_title: str = "", company: str = "",
              api_key: str | None = None, model: str | None = None, client=None) -> dict:
    """Call Claude and return the parsed JSON plus an honesty check. `client` can be injected for tests."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
    import config
    msg = client.messages.create(
        model=model or getattr(config, "TAILOR_MODEL", "claude-sonnet-5-5"),
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(resume, jd, job_title, company)}],
    )
    text = "".join(getattr(b, "text", "") for b in msg.content)
    out = _parse_json(text)
    out.setdefault("changes", [])
    out.setdefault("gaps", [])
    out.setdefault("keywords_used", [])
    out["honesty_flags"] = honesty_check(resume, out.get("tailored_resume_markdown", ""))
    return out


def honesty_check(original: str, tailored: str) -> dict:
    """Things in the tailored resume that the original never mentioned. Review these before sending."""
    new_skills = sorted(extract_skills(tailored) - extract_skills(original))
    nums = lambda t: set(re.findall(r"\d+(?:\.\d+)?\s?%|\$\s?\d[\d,.]*\s?[kKmMbB]?|\b\d{2,}\b", t))
    new_numbers = sorted(nums(tailored) - nums(original))
    return {"new_skills": new_skills, "new_numbers": new_numbers}


# --------------------------------------------------------------------------- #
# Part 3: Markdown -> DOCX
# --------------------------------------------------------------------------- #
def _add_runs(par, text: str):
    for i, chunk in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if chunk:
            par.add_run(chunk).bold = bool(i % 2)


def markdown_to_docx(md: str) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, Inches

    doc = Document()
    for s in doc.sections:
        s.top_margin = s.bottom_margin = Inches(0.6)
        s.left_margin = s.right_margin = Inches(0.7)
    base = doc.styles["Normal"]
    base.font.name, base.font.size = "Calibri", Pt(10.5)
    base.paragraph_format.space_after = Pt(2)

    first_line_done = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("# "):
            p = doc.add_paragraph()
            r = p.add_run(line[2:].strip()); r.bold = True; r.font.size = Pt(18)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            first_line_done = True
        elif line.startswith("## "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            r = p.add_run(line[3:].strip().upper()); r.bold = True; r.font.size = Pt(11.5)
        elif line.startswith("### "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            _add_runs(p, "**" + line[4:].strip().replace("**", "") + "**")
        elif _BULLET.match(line):
            p = doc.add_paragraph(style="List Bullet")
            _add_runs(p, _BULLET.sub("", line))
        else:
            p = doc.add_paragraph()
            _add_runs(p, line.strip())
            if first_line_done and len(doc.paragraphs) <= 3:   # contact line under the name
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
