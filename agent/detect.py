"""Work out which careers system a company uses from its careers page, so it can be
read directly. Results are cached in config/ats_cache.json and re-checked every 14 days."""
from __future__ import annotations
import re
from urllib.parse import urljoin, urlparse

from .http import Http

PATTERNS = [
    ("workday", re.compile(r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)")),
    ("workday_site", re.compile(r"https?://(wd\d+)\.myworkdaysite\.com/(?:[a-z]{2}-[A-Z]{2}/)?recruiting/([\w-]+)/([\w-]+)")),
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)")),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([\w-]+)")),
    ("lever", re.compile(r"jobs\.lever\.co/([\w.-]+)")),
    ("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([\w-]+)")),
]
IGNORE_WORKDAY_SITES = {"wday", "login", "refreshFacet"}


def detect_from_html(html: str, page_url: str) -> dict | None:
    for kind, rx in PATTERNS:
        for m in rx.finditer(html):
            if kind == "workday":
                tenant, wd, site = m.group(1), m.group(2), m.group(3)
                if site in IGNORE_WORKDAY_SITES:
                    continue
                return {"type": "workday", "host": f"{tenant}.{wd}.myworkdayjobs.com", "tenant": tenant, "site": site}
            if kind == "workday_site":
                wd, tenant, site = m.group(1), m.group(2), m.group(3)
                return {"type": "workday", "host": f"{tenant}.{wd}.myworkdayjobs.com", "tenant": tenant, "site": site}
            if kind == "greenhouse":
                if m.group(1) in ("embed", "v1"):
                    continue
                return {"type": "greenhouse", "board": m.group(1)}
            if kind == "lever":
                return {"type": "lever", "company_id": m.group(1)}
            if kind == "smartrecruiters":
                if m.group(1).lower() in ("oneclick-ui", "company", "static"):
                    continue
                return {"type": "smartrecruiters", "company_id": m.group(1)}
    # SuccessFactors RMK sites host assets on rmkcdn and have /search/ + /job/ paths
    if "rmkcdn.successfactors.com" in html or re.search(r'class="jobTitle-link"', html):
        p = urlparse(page_url)
        return {"type": "successfactors", "base": f"{p.scheme}://{p.netloc}"}
    if "phApp.ddo" in html or "phenompeople" in html:
        p = urlparse(page_url)
        m = re.search(r"/([a-z]{2,6}/[a-z]{2})/", p.path + "/")
        return {"type": "phenom", "base": f"{p.scheme}://{p.netloc}", "locale": m.group(1) if m else "global/en"}
    return None


def _career_links(html: str, base: str) -> list[str]:
    """Links on a careers landing page that probably lead to the real job search."""
    links = re.findall(r'href=["\']([^"\']+)["\']', html)
    out = []
    for h in links:
        hl = h.lower()
        if any(w in hl for w in ("myworkdayjobs", "greenhouse", "lever.co", "smartrecruiters", "successfactors",
                                  "/jobs", "job-search", "search-jobs", "careers/search", "opportunities", "openings", "portal")):
            out.append(urljoin(base, h))
    seen, uniq = set(), []
    for u in out:
        if u not in seen and u.startswith("http"):
            seen.add(u)
            uniq.append(u)
    return uniq[:6]


def detect(http: Http, careers_url: str) -> dict | None:
    r = http.get(careers_url)
    html, final = r.text, r.url
    found = detect_from_html(html, final)
    if found:
        return found
    for link in _career_links(html, final):   # one hop deeper
        found = detect_from_html(link, link)
        if found:
            return found
        try:
            r2 = http.get(link)
            found = detect_from_html(r2.text, r2.url)
            if found:
                return found
        except Exception:
            continue
    return None
