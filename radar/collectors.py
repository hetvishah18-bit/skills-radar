"""Collectors for companies' own career-site systems (public, no API key). Each yields normalized jobs.

These ARE the companies' career pages: when a company publishes a job, its careers page and these
endpoints update at the same moment. (LinkedIn/Indeed copy them later.)

Normalized job: {job_key, source, company, title, location, url, description, posted_at}
posted_at: ISO-8601 UTC timestamp ("2026-11-11T15:04:05Z") or a plain date ("2026-11-11") when the
source only gives a day. None if unknown (then the collection day is used).
"""
import datetime as dt
import re
import time
from typing import Iterator

import requests

import config
from radar.location import is_us

HEADERS = {"User-Agent": "skills-radar/0.3 (personal research project)", "Accept": "application/json"}
COMPANY_NAMES: dict[str, dict[str, str]] = {}   # filled from data/discovered_companies.json
OK_PREFIXES: set[str] = set()                   # job_key prefixes of boards fetched OK this run


def _prefix(source: str, arg) -> str:
    if source == "workday":
        return f"workday:{arg['tenant']}"
    if source == "remotive":
        return "remotive"
    return f"{source}:{arg}"


def _name(system: str, key: str) -> str:
    return COMPANY_NAMES.get(system, {}).get(key) or key


import threading
from urllib.parse import urlparse

_HOST_LOCKS: dict[str, threading.Semaphore] = {}
_HOST_LOCKS_GUARD = threading.Lock()
_RETRY_STATUS = {429, 500, 502, 503, 504}
RATE_LIMITED = threading.Event()   # set when a server tells us to slow down


def _host_slot(url: str) -> threading.Semaphore:
    """Limit how many requests go to the SAME server at once (most boards share one Greenhouse server)."""
    host = urlparse(url).netloc
    with _HOST_LOCKS_GUARD:
        if host not in _HOST_LOCKS:
            _HOST_LOCKS[host] = threading.Semaphore(getattr(config, "MAX_PER_SERVER", 3))
        return _HOST_LOCKS[host]


def _request(method: str, url: str, **kw):
    """HTTP with polite retries: waits and retries on timeouts, 429 'too many requests' and server errors."""
    tries = getattr(config, "RETRIES", 3)
    headers = kw.pop("headers", HEADERS)
    for attempt in range(tries + 1):
        try:
            with _host_slot(url):
                r = requests.request(method, url, headers=headers, timeout=config.REQUEST_TIMEOUT, **kw)
            if r.status_code in _RETRY_STATUS and attempt < tries:
                if r.status_code == 429:
                    RATE_LIMITED.set()
                wait = r.headers.get("Retry-After")
                time.sleep(min(int(wait), 120) if wait and wait.isdigit() else 3 * 2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()
        except (requests.Timeout, requests.ConnectionError):
            if attempt == tries:
                raise
            time.sleep(3 * 2 ** attempt)


def _get(url: str, params: dict | None = None):
    return _request("GET", url, params=params)


def _post(url: str, payload: dict):
    return _request("POST", url, json=payload, headers={**HEADERS, "Content-Type": "application/json"})


def to_utc_iso(value) -> str | None:
    """Normalize ISO strings / epoch-ms / dates to 'YYYY-MM-DDTHH:MM:SSZ' (UTC)."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            t = dt.datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=dt.timezone.utc)
        else:
            s = str(value).strip().replace("Z", "+00:00")
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
                return s
            t = dt.datetime.fromisoformat(s)
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
        return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError, OSError):
        return None


# --- Greenhouse --------------------------------------------------------------
def greenhouse(board: str) -> Iterator[dict]:
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", {"content": "true"})
    for j in data.get("jobs", []):
        yield {
            "job_key": f"greenhouse:{board}:{j['id']}",
            "source": "greenhouse",
            "company": j.get("company_name") or _name("greenhouse", board),
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "description": j.get("content", ""),  # HTML-escaped; cleaned in skills.clean_text
            "posted_at": to_utc_iso(j.get("first_published")),
        }


# --- Lever -------------------------------------------------------------------
def lever(company: str) -> Iterator[dict]:
    data = _get(f"https://api.lever.co/v0/postings/{company}", {"mode": "json"})
    for j in data:
        lists = " ".join(f"{l.get('text', '')} {l.get('content', '')}" for l in j.get("lists", []))
        yield {
            "job_key": f"lever:{company}:{j['id']}",
            "source": "lever",
            "company": _name("lever", company),
            "title": j.get("text", ""),
            "location": (j.get("categories") or {}).get("location", ""),
            "url": j.get("hostedUrl", ""),
            "description": f"{j.get('descriptionPlain', '')} {lists} {j.get('additionalPlain', '')}",
            "posted_at": to_utc_iso(j.get("createdAt")),
        }


# --- Ashby (OpenAI, Notion, Ramp, ...) ---------------------------------------
def ashby(board: str) -> Iterator[dict]:
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{board}", {"includeCompensation": "true"})
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [
            (s.get("location") if isinstance(s, dict) else str(s)) or "" for s in j.get("secondaryLocations") or []]
        addr = ((j.get("address") or {}).get("postalAddress") or {})
        if addr.get("addressCountry"):
            locs.append(f"{addr.get('addressLocality', '')}, {addr.get('addressRegion', '')}, {addr['addressCountry']}")
        if j.get("isRemote") and not any("remote" in l.lower() for l in locs):
            locs.append("Remote")
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        yield {
            "job_key": f"ashby:{board}:{j['id']}",
            "source": "ashby",
            "company": _name("ashby", board),
            "title": j.get("title", ""),
            "location": "; ".join(l for l in locs if l.strip(" ,")),
            "url": j.get("jobUrl") or f"https://jobs.ashbyhq.com/{board}/{j['id']}",
            "description": (j.get("descriptionPlain") or j.get("descriptionHtml") or "") + (f" Compensation: {comp}" if comp else ""),
            "posted_at": to_utc_iso(j.get("publishedAt")),
        }


# --- Workday (Nvidia, Adobe, Walmart, Capital One, ...) ----------------------
_WD_POSTED = re.compile(r"posted\s+(today|yesterday|(\d+)\+?\s+days?\s+ago)", re.I)


def workday_posted_date(posted_on: str | None, today: dt.date | None = None) -> str | None:
    """'Posted Today' / 'Posted Yesterday' / 'Posted 3 Days Ago' / 'Posted 30+ Days Ago' -> date."""
    m = _WD_POSTED.search(posted_on or "")
    if not m:
        return None
    today = today or dt.datetime.now(dt.timezone.utc).date()
    w = m.group(1).lower()
    days = 0 if w == "today" else 1 if w == "yesterday" else int(m.group(2))
    return (today - dt.timedelta(days=days)).isoformat()


def workday(site: dict) -> Iterator[dict]:
    """site = {"company": "Nvidia", "host": "nvidia.wd5.myworkdayjobs.com", "tenant": "nvidia",
               "site": "NVIDIAExternalCareerSite"}. Searches each role keyword, then opens matching jobs."""
    host, tenant, name = site["host"], site["tenant"], site["site"]
    base = f"https://{host}/wday/cxs/{tenant}/{name}"
    seen: set[str] = set()
    max_pages = getattr(config, "WORKDAY_MAX_PAGES", 5)
    for q in getattr(config, "WORKDAY_SEARCHES", [""]):
        for page in range(max_pages):
            data = _post(f"{base}/jobs", {"appliedFacets": {}, "limit": 20, "offset": page * 20, "searchText": q})
            posts = data.get("jobPostings") or []
            for p in posts:
                path = p.get("externalPath")
                if not path or path in seen:
                    continue
                seen.add(path)
                title = p.get("title", "")
                if not match_role(title):                       # only open the jobs we care about
                    continue
                loc_list = p.get("locationsText", "")
                if config.US_ONLY and loc_list and "location" not in loc_list.lower() and not is_us(loc_list):
                    continue                                    # clearly non-US (skip the detail call)
                try:
                    info = (_get(f"{base}{path}") or {}).get("jobPostingInfo") or {}
                except Exception:
                    info = {}
                locs = [info.get("location") or loc_list] + list(info.get("additionalLocations") or [])
                posted = to_utc_iso(info.get("startDate")) or workday_posted_date(p.get("postedOn"))
                yield {
                    "job_key": f"workday:{tenant}:{info.get('jobReqId') or (p.get('bulletFields') or [path])[0]}",
                    "source": "workday",
                    "company": site.get("company") or tenant,
                    "title": title,
                    "location": "; ".join(l for l in locs if l),
                    "url": info.get("externalUrl") or f"https://{host}/{name}{path}",
                    "description": info.get("jobDescription", ""),
                    "posted_at": posted,
                }
                time.sleep(0.2)
            if len(posts) < 20:
                break
            time.sleep(0.3)


# --- SmartRecruiters (Visa, Bosch, AECOM, ...) -------------------------------
def smartrecruiters(company: str) -> Iterator[dict]:
    base = f"https://api.smartrecruiters.com/v1/companies/{company}/postings"
    offset, total = 0, None
    while total is None or offset < total:
        data = _get(base, {"limit": 100, "offset": offset})
        total = min(data.get("totalFound", 0), 1000)
        items = data.get("content") or []
        if not items:
            break
        for p in items:
            title = p.get("name", "")
            loc = p.get("location") or {}
            loc_text = loc.get("fullLocation") or ", ".join(
                x for x in (loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()) if x)
            if loc.get("remote"):
                loc_text += " (Remote)"
            if (loc.get("country") or "").lower() == "us" and "united states" not in loc_text.lower():
                loc_text += ", United States"
            if not match_role(title) or (config.US_ONLY and not is_us(loc_text)):
                continue
            try:
                d = _get(f"{base}/{p['id']}")
                secs = (d.get("jobAd") or {}).get("sections") or {}
                desc = " ".join((secs.get(k) or {}).get("text", "") for k in
                                ("jobDescription", "qualifications", "additionalInformation"))
                url = d.get("postingUrl") or d.get("applyUrl")
            except Exception:
                desc, url = "", None
            yield {
                "job_key": f"smartrecruiters:{company}:{p['id']}",
                "source": "smartrecruiters",
                "company": (p.get("company") or {}).get("name") or _name("smartrecruiters", company),
                "title": title,
                "location": loc_text,
                "url": url or f"https://jobs.smartrecruiters.com/{company}/{p['id']}",
                "description": desc,
                "posted_at": to_utc_iso(p.get("releasedDate")),
            }
            time.sleep(0.1)
        offset += len(items)


# --- One Workday job from its link (used for listed jobs) --------------------
_WD_URL = re.compile(r"https?://(([a-z0-9-]+)\.wd\d+\.myworkdayjobs\.com)/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)(/job/[^?#]+)")


def workday_job(url: str) -> dict | None:
    m = _WD_URL.search(url or "")
    if not m:
        return None
    host, tenant, site, path = m.groups()
    path = re.sub(r"/apply(?:/.*)?$", "", path)
    info = (_get(f"https://{host}/wday/cxs/{tenant}/{site}{path}") or {}).get("jobPostingInfo") or {}
    if not info:
        return None
    locs = [info.get("location") or ""] + list(info.get("additionalLocations") or [])
    return {
        "job_key": f"workday:{tenant}:{info.get('jobReqId') or path}",
        "source": "workday",
        "company": None,
        "title": info.get("title", ""),
        "location": "; ".join(l for l in locs if l),
        "url": info.get("externalUrl") or url,
        "description": info.get("jobDescription", ""),
        "posted_at": to_utc_iso(info.get("startDate")),
    }


# --- Listed jobs (from the discovery lists) ----------------------------------
_SPONSOR_TEXT = {"U.S. Citizenship is Required": "U.S. citizenship is required.",
                 "Does Not Offer Sponsorship": "Sponsorship is not available for this role.",
                 "Offers Sponsorship": "Visa sponsorship is available."}


def listing_job(x: dict) -> dict:
    """A list entry as a job (title, company, location, date, link). No description."""
    locs = x.get("locations") or []
    return {
        "job_key": f"list:{x.get('source', 'list').lower()}:{x['id']}",
        "source": "list",
        "company": x.get("company_name", ""),
        "title": x.get("title", ""),
        "location": "; ".join(locs),
        "url": re.sub(r"[?&]utm_source=Simplify.*$", "", x.get("url", "")),
        "description": _SPONSOR_TEXT.get(x.get("sponsorship"), ""),
        "posted_at": to_utc_iso(x.get("date_posted")),
    }


# --- Remotive (remote-only job board) ----------------------------------------
def remotive(search: str) -> Iterator[dict]:
    data = _get("https://remotive.com/api/remote-jobs", {"search": search})
    for j in data.get("jobs", []):
        yield {
            "job_key": f"remotive:{j['id']}",
            "source": "remotive",
            "company": j.get("company_name", ""),
            "title": j.get("title", ""),
            "location": j.get("candidate_required_location", "Remote"),
            "url": j.get("url", ""),
            "description": j.get("description", ""),
            "posted_at": to_utc_iso(j.get("publication_date")),
        }


# --- filtering ---------------------------------------------------------------
_ROLE_RX = {role: re.compile("|".join(p), re.I) for role, p in config.TARGET_ROLES.items()}
_EARLY_RX = re.compile(config.EARLY_CAREER_PATTERN, re.I) if config.EARLY_CAREER_PATTERN else None


def match_role(title: str) -> str | None:
    if _EARLY_RX and not _EARLY_RX.search(title):
        return None
    for role, rx in _ROLE_RX.items():
        if rx.search(title):
            return role
    return None


def _run(source: str, label: str, fn, arg) -> tuple[str, str, list[dict], int, str | None]:
    """Fetch one company/source. Returns (source, label, jobs, skipped_non_us, error)."""
    out, skipped = [], 0
    try:
        for job in fn(arg):
            role = match_role(job["title"])
            if not role:
                continue
            if config.US_ONLY and not is_us(job.get("location")):
                skipped += 1
                continue
            job["role"] = role
            out.append(job)
        return source, label, out, skipped, None
    except Exception as e:  # one bad site shouldn't kill the run
        return source, label, out, skipped, f"{e.__class__.__name__}: {str(e)[:100]}"


FAILS_FILE = None   # set in collect_all


def _load_fails() -> dict:
    import json
    try:
        return json.loads(FAILS_FILE.read_text())
    except Exception:
        return {}


def collect_all(log=print) -> Iterator[dict]:
    """Run every configured + discovered source in parallel; skip (and log) any that fail."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from radar import discovery

    discovered, listings = ({}, [])
    if getattr(config, "DISCOVER_COMPANIES", False):
        discovered, listings = discovery.refresh(log)
        COMPANY_NAMES.update(discovered)

    def boards(system: str, configured: list) -> list:
        return list(dict.fromkeys([*configured, *discovered.get(system, {})]))

    tasks = [("greenhouse", b, greenhouse, b) for b in boards("greenhouse", config.GREENHOUSE_BOARDS)]
    tasks += [("lever", c, lever, c) for c in boards("lever", config.LEVER_COMPANIES)]
    tasks += [("ashby", b, ashby, b) for b in boards("ashby", getattr(config, "ASHBY_BOARDS", []))]
    tasks += [("smartrecruiters", c, smartrecruiters, c) for c in discovered.get("smartrecruiters", {})]
    tasks += [("workday", s.get("company") or s["tenant"], workday, s) for s in getattr(config, "WORKDAY_SITES", [])]
    tasks += [("remotive", q, remotive, q) for q in config.REMOTIVE_SEARCHES]
    arg_of = {(t[0], t[1]): t[3] for t in tasks}

    # Boards that failed 3 runs in a row are skipped, then retried once a week
    global FAILS_FILE
    import json
    FAILS_FILE = discovery.DATA / "board_failures.json"
    fails = _load_fails()
    if len(fails) > 0.3 * max(1, len(tasks)):        # recorded during an outage, not real dead boards
        log(f"  resetting the failed-board list ({len(fails):,} entries looked like an outage)")
        fails = {}
    today = dt.date.today()
    def skip(t):
        f = fails.get(f"{t[0]}:{t[1]}")
        return bool(f) and f["count"] >= 3 and (today - dt.date.fromisoformat(f["last"])).days < 7
    skipped_boards = [t for t in tasks if skip(t)]
    tasks = [t for t in tasks if not skip(t)]
    by_src: dict[str, list[int]] = {}      # source -> [ok, failed, jobs]
    err_kinds: dict[str, int] = {}

    ok_boards: set[tuple[str, str]] = set()
    seen_keys: set[str] = set()
    totals = {"companies": 0, "failed": 0, "jobs": 0}
    log(f"  fetching {len(tasks):,} company job boards ({getattr(config, 'COLLECT_THREADS', 8)} at a time)...")
    with ThreadPoolExecutor(max_workers=getattr(config, "COLLECT_THREADS", 8)) as pool:
        futures = [pool.submit(_run, *t) for t in tasks]
        for i, f in enumerate(as_completed(futures), 1):
            source, label, jobs, skipped, err = f.result()
            st_ = by_src.setdefault(source, [0, 0, 0])
            fk = f"{source}:{label}"
            if err:
                st_[1] += 1
                kind = ("timeout / connection" if any(w in err for w in ("Timeout", "timed out", "Connection"))
                        else "429 too many requests" if "429" in err
                        else "404 not found" if "404" in err else err.split(":")[0])
                err_kinds[kind] = err_kinds.get(kind, 0) + 1
                prev = fails.get(fk, {"count": 0})
                fails[fk] = {"count": prev["count"] + 1, "last": today.isoformat(), "error": err[:80]}
            else:
                st_[0] += 1
                st_[2] += len(jobs)
                fails.pop(fk, None)
            if err:
                totals["failed"] += 1
                if totals["failed"] <= 10:
                    log(f"  {source:<15} {label:<24} FAILED: {err}")
                elif totals["failed"] == 11:
                    log("  (more failures hidden; companies whose site changed are simply skipped)")
            else:
                ok_boards.add((source, label.lower() if source in ("greenhouse", "lever") else label))
                if source != "workday":        # Workday is searched by keyword, so "not found" != closed
                    OK_PREFIXES.add(_prefix(source, arg_of[(source, label)]))
                totals["companies"] += 1
                if jobs and len(tasks) <= 120:
                    log(f"  {source:<15} {label:<24} {len(jobs):>4} matching postings"
                        + (f" ({skipped} outside USA skipped)" if skipped else ""))
            for job in jobs:
                if job["job_key"] not in seen_keys:
                    seen_keys.add(job["job_key"])
                    totals["jobs"] += 1
                    yield job
            if i % 100 == 0:
                log(f"  ... {i:,}/{len(tasks):,} boards done, {totals['jobs']:,} matching jobs so far")
    log(f"  boards: {totals['companies']:,} OK, {totals['failed']:,} failed, {totals['jobs']:,} matching jobs"
        + (f" ({len(skipped_boards)} boards skipped: failed 3 runs in a row, retried weekly)" if skipped_boards else ""))
    for src, (ok, bad, n) in sorted(by_src.items()):
        log(f"    {src:<16} {ok:>5} OK {bad:>4} failed {n:>6,} jobs")
    if err_kinds:
        log("  failure reasons: " + ", ".join(f"{k} {v:,}" for k, v in sorted(err_kinds.items(), key=lambda x: -x[1])))
    network_trouble = totals["failed"] > 0.3 * max(1, len(tasks))
    if network_trouble:
        log("  ⚠ Most boards failed. That's a network problem or the servers asking us to slow down (common if\n"
            "    collect.py runs several times in a short time), not dead companies. These failures are NOT\n"
            "    remembered, and no jobs were closed. Wait an hour or two and run again (once a day is plenty).")
    else:
        FAILS_FILE.parent.mkdir(parents=True, exist_ok=True)
        FAILS_FILE.write_text(json.dumps(fails, indent=1, sort_keys=True))

    # Listed jobs that the full boards didn't already cover
    if listings:
        OK_PREFIXES.add("list:simplify")
        todo_wd, plain = [], []
        for x in listings:
            if not match_role(x.get("title", "")):
                continue
            b = discovery.board_of(x["url"])
            if b and b[0] != "workday" and b in ok_boards:
                continue                                  # already collected from the company's board
            if b and b[0] == "workday" and getattr(config, "DISCOVERED_WORKDAY_DETAILS", True):
                todo_wd.append(x)
            else:
                plain.append(x)
        n_list = 0

        def wd(x):
            try:
                j = workday_job(x["url"])
            except Exception:
                j = None
            if j:
                j["company"] = x.get("company_name") or j["company"]
                j["posted_at"] = j["posted_at"] or to_utc_iso(x.get("date_posted"))
                return j
            return listing_job(x)

        with ThreadPoolExecutor(max_workers=getattr(config, "COLLECT_THREADS", 8)) as pool:
            for job in pool.map(wd, todo_wd):
                plain.append(job)
        for x in plain:
            job = x if "job_key" in x else listing_job(x)
            role = match_role(job["title"])
            if not role or job["job_key"] in seen_keys:
                continue
            if config.US_ONLY and not is_us(job.get("location")):
                continue
            job["role"] = role
            seen_keys.add(job["job_key"])
            n_list += 1
            yield job
        log(f"  listings   {len(listings):,} recent list entries -> {n_list:,} extra matching jobs "
            f"({len(todo_wd):,} Workday jobs opened for details)")
