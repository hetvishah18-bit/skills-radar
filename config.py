"""Edit this file to point the radar at the roles and companies you care about."""

# Role buckets: a posting is kept if its TITLE matches any pattern (case-insensitive).
# First match wins, so put more specific roles first.
TARGET_ROLES = {
    "Data Analyst":        [r"data analyst", r"analytics analyst", r"bi analyst", r"business intelligence"],
    "Business Analyst":    [r"business analyst", r"business systems analyst"],
    "Data Engineer":       [r"data engineer", r"analytics engineer"],
    "Software Engineer":   [r"software engineer", r"software developer", r"full[- ]stack", r"backend engineer", r"frontend engineer"],
    "Supply Chain Analyst": [r"supply chain analyst", r"demand planner", r"supply planner"],
    "Project Manager":     [r"project manager", r"program manager"],
}

# Optional: only keep early-career postings. Set to None to keep everything.
EARLY_CAREER_PATTERN = None   # e.g. r"new grad|entry|junior|associate|graduate|early career|\bI\b"

# Keep only jobs located in the USA (incl. "Remote - US"). Set False to keep every country.
US_ONLY = True

# --- Sources (all public, no API key needed) --------------------------------
# Greenhouse board tokens: the slug in https://boards.greenhouse.io/<token>
GREENHOUSE_BOARDS = [  # 68 boards verified working on 2026-11-09
    "andurilindustries", "spacex", "databricks", "elastic", "stripe", "roblox", "anthropic", "affirm",
    "okta", "waymo", "coinbase", "mongodb", "toast", "verkada", "cloudflare", "purestorage",
    "braze", "brex", "scaleai", "fivetran", "gitlab", "samsara", "drweng", "reddit",
    "pinterest", "lyft", "robinhood", "airbnb", "point72", "imc", "figma", "klaviyo",
    "relativity", "gusto", "janestreet", "zoominfo", "sigmacomputing", "asana", "chime", "datadog",
    "hellofresh", "instacart", "zscaler", "oscar", "flexport", "vercel", "dropbox", "twilio",
    "appian", "qualtrics", "zocdoc", "duolingo", "discord", "sofi", "attentive", "squarespace",
    "carvana", "nextdoor", "bandwidth", "faire", "jfrog", "newrelic", "mixpanel", "yext",
    "peloton", "sumologic", "calendly", "nuro",
]

# Lever company slugs: the slug in https://jobs.lever.co/<company>
LEVER_COMPANIES = [
    "plaid", "palantir", "netflix", "spotify",
]

# Ashby career sites: the slug in https://jobs.ashbyhq.com/<slug>
ASHBY_BOARDS = [
    "openai", "notion", "ramp", "linear", "anysphere", "perplexity", "deel", "vanta",
    "replit", "cohere", "elevenlabs", "harvey",
]

# Workday career sites. From a careers URL like
#   https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
# host = "nvidia.wd5.myworkdayjobs.com", site = "NVIDIAExternalCareerSite", tenant = usually the first word.
# Not sure of a company's values? Open its careers page; the address bar shows host and site.
WORKDAY_SITES = [
    {"company": "Nvidia",      "host": "nvidia.wd5.myworkdayjobs.com",     "tenant": "nvidia",     "site": "NVIDIAExternalCareerSite"},
    {"company": "Adobe",       "host": "adobe.wd5.myworkdayjobs.com",      "tenant": "adobe",      "site": "external_experienced"},
    {"company": "Salesforce",  "host": "salesforce.wd12.myworkdayjobs.com","tenant": "salesforce", "site": "External_Career_Site"},
    {"company": "Walmart",     "host": "walmart.wd5.myworkdayjobs.com",    "tenant": "walmart",    "site": "WalmartExternal"},
    {"company": "Capital One", "host": "capitalone.wd12.myworkdayjobs.com","tenant": "capitalone", "site": "Capital_One"},
    {"company": "Intel",       "host": "intel.wd1.myworkdayjobs.com",      "tenant": "intel",      "site": "External"},
    {"company": "Target",      "host": "target.wd5.myworkdayjobs.com",     "tenant": "target",     "site": "targetcareers"},
    {"company": "Mastercard",  "host": "mastercard.wd1.myworkdayjobs.com", "tenant": "mastercard", "site": "CorporateCareers"},
]
# Workday sites can have thousands of jobs, so we search them by these keywords only.
WORKDAY_SEARCHES = ["data analyst", "business analyst", "data engineer", "software engineer",
                    "supply chain analyst", "project manager"]
WORKDAY_MAX_PAGES = 5   # x 20 results per keyword per company

# --- Company auto-discovery ---------------------------------------------------
# Public, community-maintained job lists (updated daily). collect.py reads them, adds every company it
# can find to data/discovered_companies.json, collects their full job boards, and also adds the listed
# jobs themselves (title + link) for companies on systems we can't read in full (Apple, TikTok, ...).
DISCOVER_COMPANIES = True
DISCOVERY_LISTS = [
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
]
LISTINGS_MAX_DAYS = 60          # ignore list entries posted longer ago than this
DISCOVERED_WORKDAY_DETAILS = True   # open each listed Workday job for its description (slower)
COLLECT_THREADS = 8             # companies fetched in parallel

# --- Link checking (during collect.py) ------------------------------------------
# Opens job links to catch dead ones: "title + link" jobs that 404 are hidden as closed, and Greenhouse
# jobs whose company-website link is broken switch to Greenhouse's own copy of the posting.
LINK_CHECK = True
LINK_CHECK_ALL = False          # True = also check full jobs whose link isn't on the company's career system
LINK_RECHECK_DAYS = 3           # don't re-check the same link more often than this
LINK_CHECK_MAX = 1500           # cap per run (keeps collect.py from running too long)

# Remotive (remote jobs board) search terms
REMOTIVE_SEARCHES = ["data analyst", "software engineer", "business analyst", "data engineer"]

REQUEST_TIMEOUT = 45  # seconds per request (big companies' boards are several MB)
MAX_PER_SERVER = 3    # requests at once to the same server (Greenhouse hosts most boards, so be gentle)
RETRIES = 3           # retry timeouts / "too many requests" / server errors, waiting longer each time

# --- Dashboard tabs ------------------------------------------------------------
# Tabs to hide. Names: "Top skills", "Trends", "Rising / falling", "Salary by skill", "2024 vs 2026",
# "My resume gap", "🎯 Job match", "Postings", "📋 My applications"
HIDDEN_TABS = ["Rising / falling", "Salary by skill"]

# --- Resume tailoring ----------------------------------------------------------
# The free match check always shows. The AI rewrite needs a paid Anthropic API key,
# so it's hidden unless you set this to True.
SHOW_AI_TAILORING = False
TAILOR_MODEL = "claude-sonnet-5-5"   # good balance of quality and cost; "claude-opus-5-5" for best quality

# --- Email digest (python digest.py) --------------------------------------------
DIGEST_FREQUENCY = "daily"           # "daily" = jobs posted in the last 24 hours, every morning
                                     # "weekly" = last 7 days, Mondays only
DIGEST_USE_RESUME = False            # False = just the newest jobs that fit your filters, newest first
RESUME_PATH = "data/resume.pdf"      # only used if DIGEST_USE_RESUME = True
DIGEST_ROLES = ["Data Analyst", "Business Analyst", "Data Engineer", "Software Engineer",
                "Supply Chain Analyst", "Project Manager"]
DIGEST_EARLY_CAREER_ONLY = True
DIGEST_US_ONLY = True
DIGEST_HIDE_NO_SPONSOR = False       # True = leave out "no sponsorship / citizens only / clearance" jobs
DIGEST_TOP_N = 15
