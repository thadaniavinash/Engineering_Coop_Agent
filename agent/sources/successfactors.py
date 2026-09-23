"""SAP SuccessFactors career sites (the 'RMK' template: /search/?q=..., /job/.../12345/).
Reads the normal public search-results page; robots.txt on these sites allows /search/ and /job/."""
from __future__ import annotations
import re
from urllib.parse import urljoin, quote_plus

from bs4 import BeautifulSoup

from ..extract import html_to_text, iso_date
from .common import Ctx, job

PAGE = 25
MAX_PAGES = 4


def _rows(html: str, base: str):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr.data-row") or soup.select("li.job-tile") or soup.select("div.job-tile")
    out = []
    for r in rows:
        a = r.select_one("a.jobTitle-link") or r.select_one("a[href*='/job/']")
        if not a:
            continue
        loc = r.select_one(".jobLocation") or r.select_one("[class*=location]")
        dt = r.select_one(".jobDate") or r.select_one("[class*=date]")
        out.append({"title": a.get_text(" ", strip=True), "url": urljoin(base, a.get("href")),
                    "location": loc.get_text(" ", strip=True) if loc else "",
                    "date": dt.get_text(" ", strip=True) if dt else ""})
    if not out:  # fallback: any /job/ links
        for a in soup.select("a[href*='/job/']"):
            t = a.get_text(" ", strip=True)
            if t and len(t) > 4:
                out.append({"title": t, "url": urljoin(base, a.get("href")), "location": "", "date": ""})
    return out


def _detail(html: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(html, "html.parser")
    body = (soup.select_one("span.jobdescription") or soup.select_one("[itemprop=description]")
            or soup.select_one("div.job") or soup.select_one("div.jobDisplay") or soup.body or soup)
    loc_el = soup.select_one("[itemprop=jobLocation]") or soup.select_one("span.jobGeoLocation") or soup.select_one(".jobLocation")
    date_el = soup.select_one("[itemprop=datePosted]") or soup.select_one("p#job-date") or soup.select_one(".jobDate")
    date_v = (date_el.get("content") if date_el and date_el.get("content") else (date_el.get_text(" ", strip=True) if date_el else ""))
    return (html_to_text(str(body)), loc_el.get_text(" ", strip=True) if loc_el else "", date_v)


def fetch(c: dict, ctx: Ctx) -> list[dict]:
    base = c["base"].rstrip("/")
    found: dict[str, dict] = {}
    for term in ctx.settings["search_terms"]:
        for page in range(MAX_PAGES):
            url = f"{base}/search/?q={quote_plus(term)}&startrow={page * PAGE}"
            rows = _rows(ctx.http.get(url).text, base)
            new = [r for r in rows if r["url"] not in found]
            for r in rows:
                found.setdefault(r["url"], r)
            if len(rows) < PAGE or not new:
                break
    out = []
    cands = [r for r in found.values() if ctx.title_ok(r["title"]) and ctx.location_maybe(r["location"])]
    for r in cands[: ctx.settings.get("max_details_per_company", 60)]:
        desc, loc2, d2 = "", "", ""
        try:
            desc, loc2, d2 = _detail(ctx.http.get(r["url"]).text)
        except Exception as e:
            ctx.log.append(f"detail failed {r['url']}: {e}")
        m = re.search(r"/(\d{5,})/?$", r["url"])
        out.append(job(ext_id=m.group(1) if m else r["url"], title=r["title"], url=r["url"],
                       locations=[r["location"] or loc2], description=desc, posted=iso_date(r["date"] or d2)))
    return out
