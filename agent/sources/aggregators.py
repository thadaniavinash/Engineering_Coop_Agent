"""Job aggregators, used to catch employers that aren't on the company list:
Adzuna (free API key), Jooble (free API key), and Job Bank Canada (public search page)."""
from __future__ import annotations
import os
import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from ..extract import html_to_text, iso_date
from .common import Ctx, job


class NotConfigured(Exception):
    pass


def adzuna(c: dict, ctx: Ctx) -> list[dict]:
    app_id, key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and key):
        raise NotConfigured("add ADZUNA_APP_ID and ADZUNA_APP_KEY secrets to turn this on (free)")
    found = {}
    for q in ctx.settings["aggregator_queries"]:
        for page in (1, 2):
            url = (f"https://api.adzuna.com/v1/api/jobs/ca/search/{page}?app_id={app_id}&app_key={key}"
                   f"&what={quote_plus(q)}&where=Ontario&results_per_page=50&max_days_old=60&content-type=application/json")
            data = ctx.http.get_json(url, check_robots=False)
            res = data.get("results", [])
            for r in res:
                found.setdefault(str(r.get("id")), r)
            if len(res) < 50:
                break
    out = []
    for rid, r in found.items():
        title = html_to_text(r.get("title", ""))
        loc = (r.get("location") or {}).get("display_name", "")
        area = ", ".join((r.get("location") or {}).get("area", []) or [])
        if not ctx.title_ok(title):
            continue
        pay = ""
        if r.get("salary_min") and not r.get("salary_is_predicted") in ("1", 1):
            pay = f"${int(r['salary_min']):,} to ${int(r.get('salary_max') or r['salary_min']):,}"
        out.append(job(f"adzuna-{rid}", title, r.get("redirect_url"), [loc + (", " + area if area else "")],
                       html_to_text(r.get("description", "")), iso_date(r.get("created")),
                       company=(r.get("company") or {}).get("display_name"), pay_text=pay))
    return out


def jooble(c: dict, ctx: Ctx) -> list[dict]:
    key = os.environ.get("JOOBLE_API_KEY")
    if not key:
        raise NotConfigured("add a JOOBLE_API_KEY secret to turn this on (free)")
    found = {}
    for q in ctx.settings["aggregator_queries"]:
        data = ctx.http.post_json(f"https://jooble.org/api/{key}", {"keywords": q, "location": "Ontario, Canada"}, check_robots=False)
        for r in data.get("jobs", []):
            found.setdefault(str(r.get("id") or r.get("link")), r)
    out = []
    for rid, r in found.items():
        title = html_to_text(r.get("title", ""))
        if ctx.title_ok(title) and ctx.location_maybe(r.get("location", "")):
            out.append(job(f"jooble-{rid}", title, r.get("link"), [r.get("location", "")], html_to_text(r.get("snippet", "")),
                           iso_date(r.get("updated")), company=r.get("company"), pay_text=r.get("salary", "")))
    return out


def jobbank(c: dict, ctx: Ctx) -> list[dict]:
    base = "https://www.jobbank.gc.ca"
    found = {}
    for q in ctx.settings["aggregator_queries"]:
        html = ctx.http.get(f"{base}/jobsearch/jobsearch?searchstring={quote_plus(q)}&locationstring=Ontario&sort=D").text
        soup = BeautifulSoup(html, "html.parser")
        for art in soup.select("article"):
            a = art.select_one("a.resultJobItem") or art.select_one("a[href*='jobposting']")
            if not a:
                continue
            title_el = art.select_one(".noctitle")
            title = title_el.get_text(" ", strip=True) if title_el else a.get_text(" ", strip=True)
            title = re.sub(r"\s+", " ", title)
            emp = art.select_one(".business")
            loc = art.select_one(".location")
            dt = art.select_one(".date")
            pay = art.select_one(".salary")
            url = urljoin(base, a.get("href").split(";")[0])
            found.setdefault(url, dict(title=title, company=emp.get_text(" ", strip=True) if emp else None,
                                       loc=(loc.get_text(" ", strip=True) if loc else "").replace("Location", "").strip(),
                                       date=dt.get_text(" ", strip=True) if dt else "",
                                       pay=pay.get_text(" ", strip=True) if pay else ""))
    out = []
    for url, r in found.items():
        if not ctx.title_ok(r["title"]):
            continue
        desc = ""
        try:
            s = BeautifulSoup(ctx.http.get(url).text, "html.parser")
            el = s.select_one("div.job-posting-details-body") or s.select_one("main") or s.body
            desc = html_to_text(str(el))
        except Exception as e:
            ctx.log.append(f"detail failed {url}: {e}")
        m = re.search(r"jobposting/(\d+)", url)
        out.append(job(f"jobbank-{m.group(1) if m else url}", r["title"], url, [r["loc"] + ", ON" if r["loc"] else ""],
                       desc, iso_date(r["date"]), company=r["company"], pay_text=r["pay"]))
        if len(out) >= 40:
            break
    return out
