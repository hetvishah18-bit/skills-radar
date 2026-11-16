"""Decide whether a posting's location is in the United States.

Job boards write locations many ways ("San Francisco, CA", "Remote - US", "NYC; London",
"United States", "Bengaluru, India"). A posting counts as US if ANY of its locations is US.
"""
import re

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}
US_CITIES = [
    "san francisco", "new york", "nyc", "seattle", "los angeles", "austin", "boston", "chicago",
    "denver", "atlanta", "miami", "san jose", "palo alto", "mountain view", "menlo park",
    "sunnyvale", "redmond", "bellevue", "san diego", "portland", "washington, d.c", "dallas",
    "houston", "phoenix", "philadelphia", "pittsburgh", "salt lake city", "raleigh", "detroit",
    "minneapolis", "nashville", "irvine", "santa monica", "hawthorne", "costa mesa", "brooklyn",
    "bay area", "silicon valley", "long beach", "ontario, ca", "des plaines", "las vegas",
    "cincinnati", "sacramento", "indianapolis", "st. louis", "saint louis", "charlotte", "cleveland",
    "buffalo", "greensboro", "flagstaff", "topeka", "columbus", "kansas city", "baltimore", "orlando",
    "tampa", "san antonio", "oakland", "milwaukee", "richmond", "jacksonville", "albuquerque",
    "omaha", "tulsa", "boise", "honolulu", "new orleans", "hartford", "providence", "madison",
    "ann arbor", "durham", "boulder", "scottsdale", "plano", "jersey city", "stamford", "cambridge, ma",
]

_US_WORDS = re.compile(
    r"\b(united states|u\.s\.a?\.?|usa|us|americas?|north america)\b"
    r"|\b(" + "|".join(map(re.escape, (n.lower() for n in STATES.values()))) + r")\b"
    r"|\b(" + "|".join(map(re.escape, US_CITIES)) + r")\b",
    re.I,
)
# ", CA" / " - NY" / "(TX)" style state codes; uppercase only so "in", "or", "me" don't match
_STATE_CODE = re.compile(r"(?:,|\s-|\()\s*(" + "|".join(STATES) + r")\b(?!\w)")
# Places that look US-ish but aren't (checked per segment)
_NOT_US = re.compile(r"\b(new south wales|ontario, canada|toronto|vancouver|georgia \(country\)|tbilisi"
                     r"|washington, uk|perth|london|dublin|mexico|india|canada)\b", re.I)


def is_us(location: str | None) -> bool:
    if not location or not isinstance(location, str):
        return False
    for part in re.split(r"[;|/]| or |\n", location):
        part = part.strip()
        if not part:
            continue
        if _STATE_CODE.search(part):          # "Dublin, CA", "Vancouver, WA" -> US
            return True
        if _NOT_US.search(part) and not re.search(r"\b(united states|usa)\b", part, re.I):
            continue
        if _US_WORDS.search(part):
            return True
    return False
