"""Turn raw postings into ranked, de-duplicated records and merge them with yesterday's data."""
from __future__ import annotations
import hashlib
import re
from datetime import date

from . import extract as X
from .geo import combine

SNIPPET = 700
DETAIL_MAX = 8000


def make_id(source: str, ext_id: str) -> str:
    return hashlib.sha1(f"{source}|{ext_id}".encode()).hexdigest()[:12]


def _norm_title(t: str) -> str:
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t.lower())
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def normalize(raw: dict, src: dict, settings: dict, today: date, trusted: bool = False):
    """Return (record, full_description) or (None, reason).
    trusted=True (postings hand-picked by the weekly Claude task) skips the keyword gate."""
    title = X.html_to_text(raw["title"])
    desc = raw.get("description") or ""
    text = f"{title}. {desc} {raw.get('pay_text', '')}"
    home = (settings["home"]["lat"], settings["home"]["lon"])
    g = combine(raw["locations"] or [""], home)
    if g["region"] in ("other-canada", "foreign"):
        return None, "outside Ontario"
    keep, why = X.is_relevant(title, desc, settings)
    if not keep and not (trusted and why == "no keyword match"):
        return None, why
    months = X.term_months(text)
    kws = X.keyword_hits(text, settings["keywords"])
    skills = X.skill_hits(text, settings.get("bonus_skills", []))
    loc_label = g["city"] or next((l for l in raw["locations"] if l), "") or ""
    rec = {
        "id": make_id(src["name"], raw["ext_id"]),
        "title": title,
        "company": raw.get("company") or src.get("display_name") or src["name"],
        "sector": src.get("sector", ""),
        "url": raw["url"],
        "source": src["name"],
        "source_type": src.get("type", ""),
        "city": g["city"],
        "location": loc_label[:80],
        "region": g["region"],
        "km": g["km"],
        "mode": X.work_mode(text) or ("Remote" if g["remote"] else ""),
        "term": X.term_label(months),
        "term_months": months,
        "start": X.start_date(text, earliest_year=today.year),
        "pay": X.pay_range(f"{raw.get('pay_text', '')} {desc}"),
        "kw": kws,
        "skills": skills,
        "match": X.match_score(title, kws, skills, len(settings["keywords"])),
        "citizen": X.needs_clearance(text),
        "posted": raw.get("posted"),
        "deadline": X.deadline(desc),
        "snippet": desc[:SNIPPET],
    }
    return rec, desc[:DETAIL_MAX]


def _norm_company(c: str) -> str:
    c = re.sub(r"\b(inc|ltd|limited|corp|corporation|company|co|canada|international|ulc|llc|group|of)\b\.?", " ", (c or "").lower())
    return re.sub(r"[^a-z]", "", c)[:10]


def dedupe(records: list[dict]) -> list[dict]:
    """The same job often appears on a company site and on an aggregator. Keep the company-site copy."""
    agg = {"adzuna", "jooble", "jobbank", "claude"}
    best: dict[tuple, dict] = {}
    for r in records:
        key = (_norm_company(r["company"]), _norm_title(r["title"]), r.get("city") or "")
        cur = best.get(key)
        if cur is None or (cur["source_type"] in agg and r["source_type"] not in agg):
            best[key] = r
    by_id = {}
    for r in best.values():
        by_id[r["id"]] = r
    return list(by_id.values())


# ---------------------------------------------------------------- scoring (mirrors docs/app.js)
def components(r: dict, settings: dict, today: date) -> dict:
    km = r.get("km")
    dist = 0.5 if km is None else max(0.0, 1 - km / 200)
    pay = 0.4
    if r.get("pay"):
        mid = (r["pay"][0] + r["pay"][1]) / 2
        pay = min(1, max(0, (mid - 18) / (34 - 18)))
    term = {"16": 1, "12": 1, "12-16": 1, "unclear": 0.45, "other": 0.1}.get(r.get("term"), 0.45)
    start = 0.45
    if r.get("start") and r["start"] != "unclear":
        y, m = map(int, r["start"].split("-"))
        ey, em = map(int, settings["earliest_start"].split("-"))
        diff = (y * 12 + m) - (ey * 12 + em)
        start = 0.1 if diff < 0 else (1 if diff == 0 else max(0.5, 1 - diff * 0.06))
    fresh = 0.5
    if r.get("posted"):
        try:
            days = (today - date.fromisoformat(r["posted"])).days
            fresh = min(1, max(0, 1 - days / 45))
        except ValueError:
            pass
    return {"match": r.get("match", 0), "dist": dist, "term": term, "start": start, "pay": pay, "fresh": fresh}


def score(r: dict, settings: dict, today: date) -> int:
    w = settings["weights"]
    c = components(r, settings, today)
    tw = sum(w.values()) or 1
    return round(100 * sum(c[k] * w[k] for k in w) / tw)


# ---------------------------------------------------------------- merge with history
def merge(old: list[dict], new: list[dict], ok_sources: set[str], today: date, close_after: int) -> list[dict]:
    old_by = {r["id"]: r for r in old}
    out = {}
    t = today.isoformat()
    for r in new:
        prev = old_by.get(r["id"])
        if prev:
            r["first_seen"] = prev.get("first_seen", t)
            for k in ("summary", "summary_date", "fit_notes"):
                if prev.get(k):
                    r[k] = prev[k]
        else:
            r["first_seen"] = t
        r["last_seen"] = t
        r["missed"] = 0
        r["active"] = True
        out[r["id"]] = r
    for rid, r in old_by.items():
        if rid in out:
            continue
        if r["source"] in ok_sources and r.get("missed_on") != t:
            r["missed"] = r.get("missed", 0) + 1
            r["missed_on"] = t
            if r["missed"] >= close_after:
                r["active"] = False
        # drop closed listings a month after they were last seen
        try:
            if not r.get("active", True) and (today - date.fromisoformat(r.get("last_seen", t))).days > 30:
                continue
        except ValueError:
            pass
        out[rid] = r
    for r in out.values():
        r["is_new"] = r.get("first_seen") == t and r.get("active", True)
    return list(out.values())
