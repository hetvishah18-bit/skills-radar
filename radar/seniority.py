"""Infer career level from a posting's title, description and (if the source has one) its level field.

Levels: "Internship", "Early career", "Mid", "Senior", "Not stated"
Order of evidence: source field (LinkedIn) > title keywords > years of experience in the description.
"""
import re

LEVELS = ["Early career", "Internship", "Mid", "Senior", "Not stated"]

_INTERN = re.compile(r"\b(intern|internship|co-?op|summer student)\b", re.I)
_SENIOR = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|director|head of|vp|vice president|chief|architect|"
    r"distinguished|fellow|engineering manager|manager,? (?:software |data )?engineering|manager of|senior manager)\b", re.I)
# "Software Engineer II", "Data Analyst 3", "Engineer, Level 4"
_LEVEL_NUM = re.compile(r"(?:\b(?:II|III|IV|V)\b|\b(?:level\s*)?[2-6]\b)(?!\s*(?:years?|\+|-|–|/))")
_EARLY = re.compile(
    r"\b(new grad(?:uate)?s?|graduate|entry[- ]level|entry|junior|jr\.?|associate|early[- ]career|"
    r"university|campus|apprentice(?:ship)?|rotational|fellowship program|class of 20\d\d|20(?:26|27) grad)\b"
    r"|\b(?:engineer|analyst|developer|scientist)\s+(?:I|1)\b(?!\s*[-–/])", re.I)

# "3+ years", "2-4 years", "at least 5 years", "minimum of 1 year" ... near the word "experience"
_YEARS = re.compile(
    r"(?:at least|minimum(?: of)?|min\.?)?\s*(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?\+?\s*"
    r"(?:years?|yrs?)\b[^.;]{0,60}?\bexperience", re.I)


def min_years(text: str | None) -> int | None:
    if not text:
        return None
    vals = [int(m.group(1)) for m in _YEARS.finditer(text)]
    vals = [v for v in vals if 0 <= v <= 15]
    return min(vals) if vals else None


def _by_years(yrs: int) -> str:
    return "Early career" if yrs <= 2 else "Mid" if yrs <= 4 else "Senior"


def infer_level(title: str | None, description: str | None = None, source_level: str | None = None) -> str:
    """Evidence order: intern/senior words in the title > years of experience asked >
    early-career words in the title > the job site's own level label."""
    title = title or ""
    sl = source_level.lower() if isinstance(source_level, str) else ""
    yrs = min_years(description)

    if _INTERN.search(title) or "intern" in sl:
        return "Internship"
    if _SENIOR.search(title):
        return "Mid" if yrs is not None and yrs <= 4 else "Senior"
    if _LEVEL_NUM.search(title):                      # "Engineer II", "Level 3"
        return "Senior" if yrs is not None and yrs >= 5 else "Mid"
    if yrs is not None and yrs >= 3:                  # stated requirement beats labels
        return _by_years(yrs)
    if _EARLY.search(title) or "entry" in sl or sl == "associate":
        return "Early career"
    if yrs is not None:
        return _by_years(yrs)
    if any(k in sl for k in ("director", "executive")):
        return "Senior"
    if "mid" in sl:
        return "Mid"
    return "Not stated"
