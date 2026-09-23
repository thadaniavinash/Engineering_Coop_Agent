"""Pull structured facts out of free-text job postings: term length, start date, pay,
deadline, work mode, keyword matches, clearance requirements."""
from __future__ import annotations
import html as htmllib
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
WORDNUM = {"four": 4, "eight": 8, "twelve": 12, "sixteen": 16, "twenty": 20, "one": 1, "two": 2, "three": 3, "six": 6}
SEASON = {"winter": 1, "spring": 5, "summer": 5, "fall": 9, "autumn": 9}


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    if "&lt;" in s and "<" not in s:
        s = htmllib.unescape(s)
    if "<" in s:
        s = BeautifulSoup(s, "html.parser").get_text(" ")
    s = htmllib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- term length
_NUM = r"(\d{1,2}|four|eight|twelve|sixteen|twenty)"
_TERM_RANGE = re.compile(_NUM + r"\s*(?:-|–|—|to|or|/|and)\s*" + _NUM + r"\s*[- ]?\s*(?:months?|mos?\b|month)", re.I)
_TERM_LIST = re.compile(r"((?:\d{1,2}\s*,\s*)+\d{1,2}\s*(?:,\s*)?(?:or|and)\s*\d{1,2})\s*[- ]?\s*months?", re.I)
_TERM_SINGLE = re.compile(_NUM + r"\s*[- ]?\s*(?:months?|mos?\b|month)", re.I)
_YEAR_TERM = re.compile(r"\b(one[- ]year|1[- ]year|year[- ]long|12[- ]month)\b", re.I)


def _n(x: str) -> int:
    x = x.lower()
    return WORDNUM.get(x, int(x) if x.isdigit() else 0)


def term_months(text: str) -> list[int]:
    found: set[int] = set()
    for m in _TERM_LIST.finditer(text):
        for n in re.findall(r"\d{1,2}", m.group(1)):
            found.add(int(n))
    for m in _TERM_RANGE.finditer(text):
        a, b = _n(m.group(1)), _n(m.group(2))
        found.update({a, b})
    for m in _TERM_SINGLE.finditer(text):
        found.add(_n(m.group(1)))
    if _YEAR_TERM.search(text):
        found.add(12)
    if not found and re.search(r"\bPEY\b", text):   # PEY placements are 12-16 months unless stated
        found.update({12, 16})
    return sorted(n for n in found if 3 <= n <= 20)


def term_label(months: list[int]) -> str:
    """'16' | '12' | '12-16' | 'other' | 'unclear'"""
    s = set(months)
    has12, has16 = 12 in s, 16 in s
    if has12 and has16:
        return "12-16"
    if has16:
        return "16"
    if has12:
        return "12"
    if any(12 < n < 16 for n in s):
        return "12-16"
    if s & {4, 8} and not (s - {3, 4, 5, 6, 8}):
        return "other"   # explicitly a 4- or 8-month term only
    return "unclear"


# ---------------------------------------------------------------- start date
_MONTH_YEAR = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?\s*(?:\d{1,2}(?:st|nd|rd|th)?)?\s*,?\s*(20\d\d)\b", re.I)
_SEASON_YEAR = re.compile(r"\b(winter|spring|summer|fall|autumn)(?:\s*/\s*(?:winter|spring|summer|fall|autumn))?\s*(?:term\s*)?,?\s*(20\d\d)\b", re.I)
_START_CTX = re.compile(r"(start(?:ing|s)?(?: date)?|commenc\w*|beginning|begin|work term|term|as of|from|available)", re.I)


def start_date(text: str, earliest_year: int = 2026) -> str:
    """Return 'YYYY-MM' of the most likely start, or 'unclear'."""
    cands = []
    for m in _MONTH_YEAR.finditer(text):
        mon, yr = MONTHS[m.group(1).lower().rstrip(".")], int(m.group(2))
        ctx = re.split(r"[.;\n]\s", text[max(0, m.start() - 60):m.start()])[-1]
        weight = 2 if _START_CTX.search(ctx) else 1
        # skip obvious deadline / posting dates
        if re.search(r"(deadline|apply by|closing|closes|posted|posting date|application)", ctx, re.I):
            weight = 0
        cands.append((weight, yr, mon))
    for m in _SEASON_YEAR.finditer(text):
        mon, yr = SEASON[m.group(1).lower()], int(m.group(2))
        cands.append((2, yr, mon))
    cands = [c for c in cands if c[0] > 0 and earliest_year <= c[1] <= earliest_year + 3]
    if not cands:
        return "unclear"
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    _, yr, mon = cands[0]
    return f"{yr}-{mon:02d}"


# ---------------------------------------------------------------- pay
_HOURLY = re.compile(
    r"\$\s?(\d{2}(?:\.\d{1,2})?)\s*(?:/h(?:r|our)?)?\s*(?:-|–|—|to)\s*\$?\s?(\d{2}(?:\.\d{1,2})?)\s*(?:CAD|CDN)?\s*(?:/|per|an|a)\s*(?:hr|hour|h)\b", re.I)
_HOURLY_SINGLE = re.compile(r"\$\s?(\d{2}(?:\.\d{1,2})?)\s*(?:CAD|CDN)?\s*(?:/|per|an|a)\s*(?:hr|hour|h)\b", re.I)
_ANNUAL = re.compile(
    r"\$\s?(\d{2,3}(?:,\d{3})|\d{2,3}(?:\.\d)?\s?[kK])\s*(?:CAD|CDN)?\s*(?:-|–|—|to)\s*\$?\s?(\d{2,3}(?:,\d{3})|\d{2,3}(?:\.\d)?\s?[kK])", re.I)


def _money(s: str) -> float:
    s = s.replace(",", "").strip()
    if s.lower().endswith("k"):
        return float(s[:-1]) * 1000
    return float(s)


def pay_range(text: str):
    """Hourly [lo, hi] in CAD, or None."""
    m = _HOURLY.search(text)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if 14 <= lo <= 80 and lo <= hi <= 90:
            return [round(lo, 2), round(hi, 2)]
    m = _ANNUAL.search(text)
    if m:
        lo, hi = _money(m.group(1)), _money(m.group(2))
        if 25000 <= lo <= 150000 and lo <= hi <= 200000:
            return [round(lo / 2080, 2), round(hi / 2080, 2)]
    m = _HOURLY_SINGLE.search(text)
    if m:
        v = float(m.group(1))
        if 14 <= v <= 80:
            return [v, v]
    return None


# ---------------------------------------------------------------- deadline
_DEADLINE = re.compile(
    r"(?:apply by|deadline(?: to apply)?|closing date|posting end date|closes(?: on)?|application(?:s)? due|accepting applications until)"
    r"\s*(?:is|:|-|on)?\s*(\w+\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+20\d\d|20\d\d-\d\d-\d\d|\d{1,2}\s+\w+\s+20\d\d)", re.I)


def parse_date(s: str):
    s = re.sub(r"(\d)(st|nd|rd|th)", r"\1", s.strip().replace(",", ""))
    for fmt in ("%B %d %Y", "%b %d %Y", "%b. %d %Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def deadline(text: str):
    m = _DEADLINE.search(text)
    if not m:
        return None
    d = parse_date(m.group(1))
    return d.isoformat() if d else None


# ---------------------------------------------------------------- misc flags
def work_mode(text: str) -> str:
    t = text.lower()
    if re.search(r"\bhybrid\b", t):
        return "Hybrid"
    if re.search(r"\b(fully remote|100% remote|remote position|work from home)\b", t):
        return "Remote"
    if re.search(r"\b(on-site|onsite|on site|in-person|in person)\b", t):
        return "On-site"
    return ""


_CLEAR = re.compile(r"(security clearance|reliability status|controlled goods|ITAR|canadian citizen|citizenship|"
                    r"permanent resident|site access security clearance|CNSC|secret clearance)", re.I)


def needs_clearance(text: str) -> bool:
    return bool(_CLEAR.search(text))


def keyword_hits(text: str, keywords: dict) -> list[str]:
    t = text.lower()
    hits = []
    for label, phrases in keywords.items():
        if any(re.search(r"(?<![a-z])" + re.escape(p.lower()) + r"(?![a-z])", t) for p in phrases):
            hits.append(label)
    return hits


def skill_hits(text: str, skills: list[str]) -> list[str]:
    out = []
    for s in skills:
        pat = r"(?<![A-Za-z])" + re.escape(s) + r"(?![A-Za-z])"
        flags = 0 if (s.isupper() and len(s) <= 4) else re.I
        if re.search(pat, text, flags):
            out.append(s)
    return out


def term_hit(text: str, terms: list[str]) -> bool:
    t = " " + text.lower() + " "
    for s in terms:
        s = s.lower()
        if len(s) <= 4:
            if re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", t):
                return True
        elif re.search(r"(?<![a-z])" + re.escape(s), t):
            return True
    return False


def is_relevant(title: str, text: str, settings: dict) -> tuple[bool, str]:
    """Decide whether a posting is a mechanical-ish student role. Returns (keep, reason)."""
    tl = title.lower()
    student = term_hit(title, settings["student_terms"]) or bool(
        re.search(r"(co-?op|internship|work term|pey)\b", text[:1500], re.I) and re.search(r"(student|intern|co-?op)", tl))
    if not student:
        return False, "not a student role"
    if term_hit(title, settings["exclude_title_terms"]) and "mechanical" not in tl:
        return False, "different discipline"
    kws = keyword_hits(title + " " + text, settings["keywords"])
    engineering = "engineer" in (tl + " " + text[:3000].lower()) or "technolog" in tl
    strong = {"Mechanical Engineering", "SolidWorks", "Manufacturing"} & set(kws)
    if strong or (engineering and kws):
        return True, "ok"
    return False, "no keyword match"


def match_score(title: str, kws: list[str], skills: list[str], n_keywords: int) -> float:
    s = len(kws) / max(1, n_keywords)
    tl = title.lower()
    if "mechanical" in tl:
        s += 0.15
    if any(k in tl for k in ("design", "manufactur", "solidworks", "product development", "systems")):
        s += 0.05
    s += min(0.1, 0.02 * len(skills))
    return round(min(1.0, s), 3)


def iso_date(v) -> str | None:
    """Best-effort conversion of assorted date strings to YYYY-MM-DD."""
    if not v:
        return None
    if isinstance(v, (int, float)):  # epoch millis
        try:
            return datetime.utcfromtimestamp(v / 1000 if v > 1e11 else v).date().isoformat()
        except Exception:
            return None
    s = str(v).strip()
    m = re.match(r"(20\d\d-\d\d-\d\d)", s)
    if m:
        return m.group(1)
    d = parse_date(s)
    return d.isoformat() if d else None


def workday_posted(s: str, today: date) -> str | None:
    """Workday 'Posted Today' / 'Posted 3 Days Ago' / 'Posted 30+ Days Ago'."""
    if not s:
        return None
    s = s.lower()
    if "today" in s:
        return today.isoformat()
    if "yesterday" in s:
        return date.fromordinal(today.toordinal() - 1).isoformat()
    m = re.search(r"(\d+)\+?\s*day", s)
    if m:
        return date.fromordinal(today.toordinal() - int(m.group(1))).isoformat()
    return iso_date(s)
