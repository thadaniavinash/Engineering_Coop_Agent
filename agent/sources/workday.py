"""Workday career sites (*.myworkdayjobs.com). Uses the same public JSON the site's own page loads."""
from __future__ import annotations
from ..extract import html_to_text, workday_posted
from .common import Ctx, job

PAGE = 20
MAX_PAGES = 5


def fetch(c: dict, ctx: Ctx) -> list[dict]:
    host, tenant, site = c["host"], c["tenant"], c["site"]
    api = f"https://{host}/wday/cxs/{tenant}/{site}"
    seen: dict[str, dict] = {}
    for term in ctx.settings["search_terms"]:
        for page in range(MAX_PAGES):
            data = ctx.http.post_json(f"{api}/jobs", {"appliedFacets": {}, "limit": PAGE, "offset": page * PAGE, "searchText": term})
            posts = data.get("jobPostings") or []
            for p in posts:
                path = p.get("externalPath")
                if not path or path in seen:
                    continue
                seen[path] = p
            total = data.get("total") or 0
            if not posts or (page + 1) * PAGE >= total:
                break

    out = []
    candidates = [(path, p) for path, p in seen.items()
                  if ctx.title_ok(p.get("title", "")) and ctx.location_maybe(p.get("locationsText", ""))]
    for path, p in candidates[: ctx.settings.get("max_details_per_company", 60)]:
        info = {}
        try:
            info = ctx.http.get_json(f"{api}{path}").get("jobPostingInfo", {})
        except Exception as e:  # keep the listing even if the detail page fails
            ctx.log.append(f"detail failed {path}: {e}")
        locs = [info.get("location") or p.get("locationsText", "")] + list(info.get("additionalLocations") or [])
        if info.get("country", {}).get("descriptor"):
            locs = [f"{l}, {info['country']['descriptor']}" if l and "canada" not in l.lower() and info['country']['descriptor'] == "Canada" else l for l in locs]
        url = info.get("externalUrl") or f"https://{host}/en-US/{site}{path}"
        desc = html_to_text(info.get("jobDescription", ""))
        out.append(job(ext_id=info.get("jobReqId") or path, title=info.get("title") or p.get("title"), url=url,
                       locations=locs, description=desc,
                       posted=(info.get("startDate") or workday_posted(p.get("postedOn", ""), ctx.today)),
                       extra={"timeType": info.get("timeType", "")}))
    return out
