"""Job links: backup links and link checking.

Backup link: every Greenhouse job also has a page hosted by Greenhouse itself
(https://job-boards.greenhouse.io/<company>/jobs/<id>). It keeps working even when the company's own
careers website has a broken link, as long as the job is open.

Link check (run by collect.py): opens job links and records whether the page still exists.
  - "title + link" jobs whose page is gone (404/410) are treated as closed and hidden.
  - Greenhouse jobs whose COMPANY-site link is broken switch to the Greenhouse backup link.
Sites that block automated checks (403, 429, timeouts) are left alone ("unknown"), never hidden.
"""
import re

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 skills-radar-linkcheck"}
_GH_KEY = re.compile(r"^greenhouse:([^:]+):(\d+)$")


def backup_url(job_key: str) -> str | None:
    m = _GH_KEY.match(job_key or "")
    return f"https://job-boards.greenhouse.io/{m.group(1)}/jobs/{m.group(2)}" if m else None


def is_greenhouse_hosted(url: str | None) -> bool:
    return bool(url) and "greenhouse.io" in url


def check_url(url: str, timeout: int = 12) -> str:
    """'ok' | 'dead' | 'unknown'."""
    if not url:
        return "unknown"
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True, stream=True)
        status, final = r.status_code, r.url
        r.close()
    except requests.RequestException:
        return "unknown"
    if status in (404, 410):
        return "dead"
    # Greenhouse sends closed jobs back to the company's job list with ?error=true
    if "greenhouse.io" in final and "error=true" in final:
        return "dead"
    if 200 <= status < 400:
        return "ok"
    return "unknown"          # 403 / 429 / 5xx: the site blocks or failed; don't guess
