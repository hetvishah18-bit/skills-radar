"""Company auto-discovery.

Downloads public, community-maintained job lists (default: SimplifyJobs' New-Grad-Positions, ~1,000+
companies, updated daily), keeps the listings, and pulls each company's hiring-system ID out of the
apply links. The radar then collects those companies' FULL job boards. The company list only grows.

Files (in data/):
    discovered_companies.json   {"greenhouse": {"stripe": "Stripe", ...}, "lever": {...}, "ashby": {...},
                                 "smartrecruiters": {...}, "workday": {"host|site": "Company", ...}}
    listings.json               latest copy of the downloaded listings
"""
import datetime as dt
import json
import re
from pathlib import Path

import requests

import config

DATA = Path(__file__).resolve().parent.parent / "data"
DISCOVERED = DATA / "discovered_companies.json"
LISTINGS = DATA / "listings.json"

PATTERNS = {
    "greenhouse": re.compile(r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_app\?for=)?([A-Za-z0-9_-]+)"),
    "lever": re.compile(r"jobs\.lever\.co/([A-Za-z0-9_.-]+)/"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)"),
    "smartrecruiters": re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    "workday": re.compile(r"https?://([a-z0-9-]+\.wd\d+\.myworkdayjobs\.com)/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)"),
}
_SKIP_GH = {"embed", "jobs", "v1"}


def board_of(url: str) -> tuple[str, str] | None:
    """('greenhouse', 'stripe') / ('workday', 'nvidia.wd5.myworkdayjobs.com|NVIDIAExternalCareerSite') / None"""
    for system, rx in PATTERNS.items():
        m = rx.search(url or "")
        if m:
            if system == "workday":
                return system, f"{m.group(1)}|{m.group(2)}"
            slug = m.group(1).lower() if system in ("greenhouse", "lever") else m.group(1)
            if system == "greenhouse" and slug in _SKIP_GH:
                return None
            return system, slug
    return None


def load_discovered() -> dict:
    if DISCOVERED.exists():
        try:
            return json.loads(DISCOVERED.read_text())
        except json.JSONDecodeError:
            pass
    return {k: {} for k in PATTERNS}


def fetch_listings(log=print) -> list[dict]:
    """Download every configured list; fall back to the last saved copy if offline."""
    out: list[dict] = []
    for url in getattr(config, "DISCOVERY_LISTS", []):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            data = r.json()
            log(f"  list       {url.split('/')[4]:<20} {len(data):>5} listings downloaded")
            out.extend(data)
        except Exception as e:
            log(f"  list       {url[:60]} FAILED: {e.__class__.__name__}")
    if out:
        DATA.mkdir(parents=True, exist_ok=True)
        LISTINGS.write_text(json.dumps(out))
    elif LISTINGS.exists():
        log("  using the last saved copy of the lists")
        out = json.loads(LISTINGS.read_text())
    return out


def active_listings(listings: list[dict], max_days: int | None = None) -> list[dict]:
    max_days = max_days or getattr(config, "LISTINGS_MAX_DAYS", 60)
    cutoff = dt.datetime.now(dt.timezone.utc).timestamp() - max_days * 86400
    return [x for x in listings if x.get("active") and x.get("is_visible", True)
            and (x.get("date_posted") or 0) >= cutoff and x.get("url")]


def refresh(log=print) -> tuple[dict, list[dict]]:
    """Update discovered_companies.json from the lists. Returns (discovered, active listings)."""
    listings = fetch_listings(log)
    found = load_discovered()
    before = sum(len(v) for v in found.values())
    for x in listings:                       # every listing ever seen, not just active: more companies
        b = board_of(x.get("url", ""))
        if b:
            system, key = b
            found.setdefault(system, {}).setdefault(key, x.get("company_name") or key)
    after = sum(len(v) for v in found.values())
    DATA.mkdir(parents=True, exist_ok=True)
    DISCOVERED.write_text(json.dumps(found, indent=1, sort_keys=True))
    log(f"  discovery  {after:,} companies known ({after - before:+,} new): "
        + ", ".join(f"{k} {len(v)}" for k, v in found.items()))
    return found, active_listings(listings)
