"""Careers systems with official public job-board APIs: Greenhouse, Lever, SmartRecruiters,
plus DirectEmployers '.jobs' sites and Tesla (best effort)."""
from __future__ import annotations
import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from ..extract import html_to_text, iso_date
from .common import Ctx, job


def greenhouse(c: dict, ctx: Ctx) -> list[dict]:
    data = ctx.http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{c['board']}/jobs?content=true")
    out = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        offices = [o.get("name", "") for o in j.get("offices", []) or []]
        if ctx.title_ok(j.get("title", "")) and any(ctx.location_maybe(l) for l in [loc] + offices):
            out.append(job(j.get("id"), j.get("title"), j.get("absolute_url"), [loc] + offices,
                           html_to_text(j.get("content", "")), iso_date(j.get("first_published") or j.get("updated_at"))))
    return out


def lever(c: dict, ctx: Ctx) -> list[dict]:
    data = ctx.http.get_json(f"https://api.lever.co/v0/postings/{c['company_id']}?mode=json")
    out = []
    for j in data if isinstance(data, list) else []:
        cat = j.get("categories") or {}
        locs = [cat.get("location", "")] + list(cat.get("allLocations") or [])
        if ctx.title_ok(j.get("text", "")) and any(ctx.location_maybe(l) for l in locs):
            lists = " ".join(f"{l.get('text', '')}: {html_to_text(l.get('content', ''))}" for l in j.get("lists") or [])
            desc = f"{j.get('descriptionPlain', '')} {lists} {j.get('additionalPlain', '')} {cat.get('commitment', '')}"
            out.append(job(j.get("id"), j.get("text"), j.get("hostedUrl"), locs, desc, iso_date(j.get("createdAt"))))
    return out


def smartrecruiters(c: dict, ctx: Ctx) -> list[dict]:
    cid = c["company_id"]
    found = {}
    for term in ctx.settings["search_terms"]:
        data = ctx.http.get_json(f"https://api.smartrecruiters.com/v1/companies/{cid}/postings?q={quote_plus(term)}&country=ca&limit=100")
        for p in data.get("content", []):
            found.setdefault(p["id"], p)
    out = []
    for pid, p in list(found.items()):
        loc = p.get("location") or {}
        loc_s = ", ".join(x for x in (loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()) if x)
        if not (ctx.title_ok(p.get("name", "")) and ctx.location_maybe(loc_s)):
            continue
        desc = ""
        try:
            d = ctx.http.get_json(f"https://api.smartrecruiters.com/v1/companies/{cid}/postings/{pid}")
            secs = ((d.get("jobAd") or {}).get("sections") or {})
            desc = html_to_text(" ".join((secs.get(k) or {}).get("text", "") for k in ("jobDescription", "qualifications", "additionalInformation")))
        except Exception as e:
            ctx.log.append(f"detail failed {pid}: {e}")
        out.append(job(pid, p.get("name"), f"https://jobs.smartrecruiters.com/{cid}/{pid}", [loc_s], desc, iso_date(p.get("releasedDate"))))
        if len(out) >= ctx.settings.get("max_details_per_company", 60):
            break
    return out


def directemployers(c: dict, ctx: Ctx) -> list[dict]:
    """'.jobs' microsites (e.g. canada.aecom.jobs, stantec.jobs). Job links end in /job/."""
    base = c["base"].rstrip("/")
    found = {}
    for term in ctx.settings["search_terms"][:4]:
        html = ctx.http.get(f"{base}/jobs/?q={quote_plus(term)}&location=Ontario").text
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if re.search(r"/job/?$", href) or re.search(r"/job/\?", href):
                url = urljoin(base + "/", href)
                title = a.get_text(" ", strip=True)
                li = a.find_parent(["li", "article", "div"])
                loc_el = li.select_one("[class*=location]") if li else None
                if title:
                    found.setdefault(url, {"title": title, "location": loc_el.get_text(" ", strip=True) if loc_el else ""})
    out = []
    for url, r in found.items():
        if not ctx.title_ok(r["title"]):
            continue
        loc = r["location"]
        if not loc:  # URL usually starts with the location slug: /toronto-on/...
            m = re.search(r"\.jobs/([a-z\-]+-(on|qc|bc|ab|mb|sk|ns|nb|nl))/", url)
            loc = m.group(1).replace("-", " ") if m else ""
        if not ctx.location_maybe(loc):
            continue
        desc = ""
        try:
            s = BeautifulSoup(ctx.http.get(url).text, "html.parser")
            el = s.select_one("#job_description") or s.select_one("[itemprop=description]") or s.select_one("main") or s.body
            desc = html_to_text(str(el))
        except Exception as e:
            ctx.log.append(f"detail failed {url}: {e}")
        out.append(job(url, r["title"], url, [loc], desc, None))
        if len(out) >= ctx.settings.get("max_details_per_company", 60):
            break
    return out


def tesla(c: dict, ctx: Ctx) -> list[dict]:
    """Tesla's careers site sits behind a bot wall; this usually reports 'blocked'."""
    data = ctx.http.get_json("https://www.tesla.com/cua-api/apps/careers/state", check_robots=False)
    lookup = data.get("lookup", {}) or {}
    locs = lookup.get("locations", {}) or {}
    out = []
    for j in data.get("listings", []) or []:
        title = j.get("t", "")
        loc = locs.get(str(j.get("l")), "") if isinstance(locs, dict) else ""
        if ctx.title_ok(title) and ("ON" in loc or "Ontario" in loc or "Canada" in loc):
            out.append(job(j.get("id"), title, f"https://www.tesla.com/en_CA/careers/search/job/{j.get('id')}", [loc], "", None))
    return out
