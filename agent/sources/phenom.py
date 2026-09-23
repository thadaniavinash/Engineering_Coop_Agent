"""Phenom People career sites (e.g. pgcareers.com, careers.rtx.com).
Search pages embed their results as JSON in `phApp.ddo = {...}`."""
from __future__ import annotations
import json
import re
from urllib.parse import quote_plus

from ..extract import html_to_text, iso_date
from .common import Ctx, job

_DDO = re.compile(r"phApp\.ddo\s*=\s*(\{.*?\});\s*phApp\.", re.S)


def _ddo(html: str) -> dict:
    m = _DDO.search(html)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")


def fetch(c: dict, ctx: Ctx) -> list[dict]:
    base, loc = c["base"].rstrip("/"), c.get("locale", "global/en").strip("/")
    found: dict[str, dict] = {}
    for term in ctx.settings["search_terms"]:
        for offset in (0, 10, 20, 30, 40):
            url = f"{base}/{loc}/search-results?keywords={quote_plus(term)}&location=Canada&from={offset}&s=1"
            d = _ddo(ctx.http.get(url).text)
            data = (d.get("eagerLoadRefineSearch") or {}).get("data") or {}
            jobs = data.get("jobs") or []
            if not d:
                raise RuntimeError("search page layout not recognised (no phApp.ddo data)")
            for j in jobs:
                found.setdefault(str(j.get("jobId") or j.get("reqId")), j)
            if len(jobs) < 10:
                break
    out = []
    cands = []
    for jid, j in found.items():
        locs = [j.get("location") or ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)]
        locs += [m.get("location", "") if isinstance(m, dict) else str(m) for m in (j.get("multi_location") or [])]
        if ctx.title_ok(j.get("title", "")) and any(ctx.location_maybe(l) for l in locs):
            cands.append((jid, j, locs))
    for jid, j, locs in cands[: ctx.settings.get("max_details_per_company", 60)]:
        url = f"{base}/{loc}/job/{jid}/{_slug(j.get('title', ''))}"
        desc = html_to_text(j.get("descriptionTeaser", ""))
        try:
            dd = _ddo(ctx.http.get(url).text)
            full = ((dd.get("jobDetail") or {}).get("data") or {}).get("job") or {}
            desc = html_to_text(full.get("description", "")) or desc
        except Exception as e:
            ctx.log.append(f"detail failed {url}: {e}")
        out.append(job(ext_id=jid, title=j.get("title"), url=url, locations=locs, description=desc,
                       posted=iso_date(j.get("postedDate") or j.get("dateCreated"))))
    return out
