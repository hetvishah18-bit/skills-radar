"""Work-authorization flags read from a posting's description.

    NO_SPONSOR  - says it won't sponsor visas, or wants people authorized "without sponsorship"
    CITIZEN     - requires US citizenship / "U.S. person" (ITAR, export control)
    CLEARANCE   - requires (or requires ability to get) a security clearance
    SPONSORS    - says visa sponsorship IS available (only when nothing negative was found)

Equal-opportunity boilerplate like "without regard to citizenship status" is NOT a flag.
"""
import re

NO_SPONSOR, CITIZEN, CLEARANCE, SPONSORS = ("No sponsorship", "Citizen / green card only", "Clearance",
                                            "Sponsors visas")
BLOCKING = {NO_SPONSOR, CITIZEN, CLEARANCE}

_V = r"(?:visa|immigration|employment|work|h-?1b|h1-?b)?\s*"
_RX = {
    NO_SPONSOR: re.compile(
        r"(?:not|unable to|cannot|can't|won't|will not|does not|do not|are not able to|is not able to|no)\s+"
        r"(?:be\s+able\s+to\s+)?(?:currently\s+)?(?:provide|offer|consider|support|accept)?\s*" + _V + r"sponsor"
        r"|sponsorship\s+(?:is\s+|will\s+)?(?:not|un)\s*(?:be\s+)?(?:available|provided|offered|supported|possible)"
        r"|without\s+(?:the\s+need\s+for\s+|requiring\s+|needing\s+|any\s+)?(?:current\s+or\s+future\s+|future\s+)?"
        + _V + r"sponsorship"
        r"|not\s+(?:be\s+)?eligible\s+for\s+" + _V + r"sponsorship"
        r"|(?:now\s+or\s+in\s+the\s+future|currently\s+or\s+in\s+the\s+future)\s+(?:require|need)s?\s+" + _V + r"sponsorship"
        r"|(?:opt|cpt|f-?1|h-?1b)\b[^.]{0,40}\b(?:not\s+(?:eligible|accepted|considered)|ineligible)",
        re.I),
    CITIZEN: re.compile(
        # "must be a U.S. citizen", "must be a (i) U.S. citizen or national, (ii) ... permanent resident"
        r"(?:must|required\s+to|need\s+to|will)\s+be\s+(?:a\s+|an\s+)?(?:\(?\s*(?:i|1|a)\s*\)\s*)?"
        r"u\.?\s?s\.?\s+(?:citizens?|nationals?|persons?)"
        # export-control language (ITAR / EAR) next to citizenship / green-card requirements
        r"|(?:itar|\bear\b|export\s+(?:control|regulation|administration|compliance)s?)[^|]{0,250}?"
        r"(?:u\.?\s?s\.?\s+(?:citizen|national|person)|permanent\s+resident|green\s+card)"
        r"|(?:u\.?\s?s\.?\s+(?:citizen|national|person)|permanent\s+resident|green\s+card)[^|]{0,250}?"
        r"(?:itar|\bear\b|export\s+(?:control|regulation|administration|compliance)s?)"
        r"|(?:only|must\s+be)\s+(?:a\s+)?(?:u\.?\s?s\.?\s+citizens?|green\s+card\s+holders?)\s+(?:or|and)\s+"
        r"(?:lawful\s+)?(?:permanent\s+residents?|green\s+card\s+holders?|u\.?\s?s\.?\s+citizens?)"
        r"|(?:must|required\s+to|need\s+to|will)\s+be\s+(?:a\s+)?u\.?\s?s\.?\s+citizens?"
        r"|u\.?\s?s\.?\s+citizenship\s+(?:is\s+)?(?:required|mandatory|needed)"
        r"|(?:requires?|requiring)\s+u\.?\s?s\.?\s+citizenship"
        r"|(?:only|open\s+to)\s+u\.?\s?s\.?\s+citizens"
        r"|u\.?\s?s\.?\s+citizens?\s+only"
        r"|\bu\.?\s?s\.?\s+persons?\b[^.]{0,80}(?:itar|export|22\s*c\.?f\.?r|required|must)"
        r"|(?:itar|export\s+control)[^.]{0,120}\bu\.?\s?s\.?\s+persons?\b",
        re.I),
    CLEARANCE: re.compile(
        r"(?:active|current|existing|secret|top\s+secret|ts/sci|ts\s*/\s*sci|dod|public\s+trust|security)\s+"
        r"(?:security\s+)?clearance"
        r"|clearance\s+(?:is\s+)?required"
        r"|(?:obtain|maintain|eligible\s+for|eligibility\s+for)\s+(?:and\s+maintain\s+)?(?:an?\s+)?"
        r"(?:active\s+)?(?:u\.?s\.?\s+)?(?:government\s+)?(?:security\s+)?clearance",
        re.I),
    SPONSORS: re.compile(
        r"(?:visa|h-?1b|immigration)\s+sponsorship\s+(?:is\s+)?(?:available|provided|offered|possible)"
        r"|(?:will|can|able\s+to|happy\s+to|open\s+to)\s+(?:provide\s+|offer\s+)?(?:visa\s+|h-?1b\s+)?sponsor(?:ship)?\b"
        r"|sponsorship\s+(?:is\s+)?available"
        r"|(?:opt|cpt|stem\s+opt)\s+(?:candidates\s+)?(?:welcome|encouraged|eligible)",
        re.I),
}


_NEGATED = re.compile(r"\b(?:no|not|without|nor)\s+(?:\w+\s+)?$", re.I)   # "No DoD clearance required"


# Cheap pre-checks: only run a flag's (slow) pattern if the posting contains one of its key words.
_HINTS = {
    NO_SPONSOR: re.compile(r"sponsor|\b(?:opt|cpt|f-?1|h-?1b?|visas?)\b", re.I),
    CITIZEN: re.compile(r"citizen|u\.?\s?s\.?\s+(?:person|national)|permanent\s+resident|green\s+card|\bitar\b|export", re.I),
    CLEARANCE: re.compile(r"clearance", re.I),
    SPONSORS: re.compile(r"sponsor|\b(?:opt|cpt)\b", re.I),
}
_ANY_HINT = re.compile("|".join(f"(?:{h.pattern})" for h in _HINTS.values()), re.I)


def work_auth_flags(description: str | None) -> list[str]:
    if not description:
        return []
    if not _ANY_HINT.search(description):
        return []
    from radar.skills import clean_text
    text = clean_text(description)
    has = {f: bool(h.search(text)) for f, h in _HINTS.items()}
    found = [f for f in (NO_SPONSOR, CITIZEN) if has[f] and _RX[f].search(text)]
    if has[CLEARANCE] and any(not _NEGATED.search(text[max(0, m.start() - 20):m.start()])
                              for m in _RX[CLEARANCE].finditer(text)):
        found.append(CLEARANCE)
    if not found and has[SPONSORS] and _RX[SPONSORS].search(text):
        found.append(SPONSORS)
    return found


def evidence(description: str | None, flag: str, width: int = 90) -> str:
    """The sentence fragment that triggered a flag, so you can check it yourself."""
    from radar.skills import clean_text
    text = clean_text(description or "")
    m = _RX[flag].search(text)
    if not m:
        return ""
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("…" if a else "") + text[a:b].strip() + ("…" if b < len(text) else "")
