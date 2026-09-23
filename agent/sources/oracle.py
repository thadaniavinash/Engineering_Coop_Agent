"""Oracle Recruiting Cloud (Candidate Experience) sites, e.g. Honeywell.
Uses the public recruitingCEJobRequisitions REST resource the careers page itself calls."""
from __future__ import annotations
from urllib.parse import quote

from ..extract import html_to_text, iso_date
from .common import Ctx, job


def _list_url(host, site, term, loc_id, offset):
    finder = (f"findReqs;siteNumber={site},facetsList=LOCATIONS,limit=25,offset={offset},"
              f"keyword=\"{term}\",sortBy=POSTING_DATES_DESC" + (f",locationId={loc_id}" if loc_id else ""))
    return (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true"
            f"&expand=requisitionList.secondaryLocations&finder={quote(finder, safe=';=,')}")


def fetch(c: dict, ctx: Ctx) -> list[dict]:
    host, loc_id = c["host"], c.get("location_id")
    site_used, found, last_err = None, {}, None
    for site in c.get("site_numbers", ["CX_1"]):
        try:
            ctx.http.get_json(_list_url(host, site, "intern", loc_id, 0))
            site_used = site
            break
        except Exception as e:
            last_err = e
    if not site_used:
        raise RuntimeError(f"could not find the Oracle site number ({last_err})")
    for term in ctx.settings["search_terms"]:
        for offset in (0, 25, 50):
            data = ctx.http.get_json(_list_url(host, site_used, term, loc_id, offset))
            items = (data.get("items") or [{}])[0].get("requisitionList") or []
            for r in items:
                found.setdefault(str(r.get("Id")), r)
            if len(items) < 25:
                break
    out = []
    cands = [(k, r) for k, r in found.items() if ctx.title_ok(r.get("Title", ""))]
    for rid, r in cands[: ctx.settings.get("max_details_per_company", 60)]:
        locs = [r.get("PrimaryLocation", "")] + [s.get("Name", "") for s in (r.get("secondaryLocations") or [])]
        if not any(ctx.location_maybe(l) for l in locs):
            continue
        desc = html_to_text(r.get("ShortDescriptionStr", ""))
        try:
            d = ctx.http.get_json(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
                                  f"?expand=all&onlyData=true&finder=ById;Id=%22{rid}%22,siteNumber={site_used}")
            it = (d.get("items") or [{}])[0]
            desc = html_to_text(" ".join(filter(None, [it.get("ExternalDescriptionStr"), it.get("ExternalResponsibilitiesStr"),
                                                        it.get("ExternalQualificationsStr"), it.get("CorporateDescriptionStr")]))) or desc
        except Exception as e:
            ctx.log.append(f"detail failed {rid}: {e}")
        url = c.get("job_url", f"https://{host}/hcmUI/CandidateExperience/en/sites/{site_used}/job/{{id}}").format(id=rid)
        out.append(job(ext_id=rid, title=r.get("Title"), url=url, locations=locs, description=desc, posted=iso_date(r.get("PostedDate"))))
    return out
