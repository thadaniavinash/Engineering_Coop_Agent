"""Co-op Scout daily run.

    python -m agent.run                 # full run (what GitHub Actions does every morning)
    python -m agent.run --no-email      # run without sending email
    python -m agent.run --only Magna    # test one company (name contains 'Magna'); writes nothing
    python -m agent.run --offline --no-email   # rebuild the website from saved data only (no web requests)
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import detect as D
from . import emailer
from .http import Http, Blocked
from .pipeline import normalize, dedupe, merge, score, make_id
from .sources import ADAPTERS, AGGREGATORS
from .sources.aggregators import NotConfigured
from .sources.common import Ctx

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "docs" / "data"
TZ = ZoneInfo("America/Toronto")
DETECT_EVERY_DAYS = 14


def load_yaml(p):
    return yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _detect_one(name, url, delay):
    try:
        return name, {"found": D.detect(Http(delay=delay), url)}
    except Exception as e:
        return name, {"found": None, "error": f"{type(e).__name__}: {str(e)[:160]}"}


def resolve_sources(settings, companies, cache, today, workers=8) -> tuple[list, list, list]:
    """Returns (runnable sources, manual list, status rows for sources that can't run)."""
    runnable, manual, status = [], [], []
    todo = []
    for c in companies:
        if c.get("disabled") or not c.get("careers_url") or c.get("type") or c.get("manual"):
            continue
        hit = cache.get(c["name"])
        age = (today - date.fromisoformat(hit.get("checked", "2000-01-01"))).days if hit else 999
        if age >= (DETECT_EVERY_DAYS if hit and hit.get("found") else 1):   # failures are retried the next day
            todo.append(c)
    if todo:
        print(f"Working out the careers system for {len(todo)} companies…", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for name, hit in ex.map(lambda c: _detect_one(c["name"], c["careers_url"], settings.get("per_host_delay_seconds", 1.0)), todo):
                cache[name] = {"checked": today.isoformat(), **hit}

    for c in companies:
        if c.get("disabled"):
            continue
        if c.get("manual"):
            manual.append({"name": c["name"], "url": c.get("manual_url", ""), "sector": c.get("sector", ""), "why": "Can't be read automatically"})
            continue
        if c.get("type"):
            runnable.append(c)
            if c.get("type") == "tesla" and c.get("manual_url"):
                manual.append({"name": c["name"], "url": c["manual_url"], "sector": c.get("sector", ""), "why": "Blocks automated tools"})
            continue
        url = c.get("careers_url")
        if not url:
            continue
        hit = cache.get(c["name"]) or {}
        if hit.get("found"):
            runnable.append({**c, **hit["found"], "detected": True})
        else:
            manual.append({"name": c["name"], "url": url, "sector": c.get("sector", ""), "why": "Careers system not recognised yet"})
            status.append({"name": c["name"], "type": "unknown", "status": "undetected", "found": 0, "kept": 0,
                           "message": hit.get("error") or "Couldn't tell which careers system this site uses, so it's listed under 'Check by hand'."})
    return runnable, manual, status


def run_source(src, settings, today):
    http = Http(delay=settings.get("per_host_delay_seconds", 1.0))
    ctx = Ctx(http=http, settings=settings, today=today)
    t0 = time.time()
    row = {"name": src["name"], "type": src.get("type"), "status": "ok", "found": 0, "kept": 0, "message": "", "seconds": 0}
    raws = []
    try:
        raws = ADAPTERS[src["type"]](src, ctx)
        row["found"] = len(raws)
    except NotConfigured as e:
        row.update(status="not-configured", message=str(e))
    except Blocked as e:
        row.update(status="blocked", message=str(e))
    except Exception as e:
        row.update(status="error", message=f"{type(e).__name__}: {str(e)[:200]}")
        if not isinstance(e, (OSError, ConnectionError)) and "requests" not in type(e).__module__:
            traceback.print_exc()   # parsing problems: show the details in the Actions log
    row["seconds"] = round(time.time() - t0, 1)
    if ctx.log:
        row["notes"] = ctx.log[:5]
    return src, raws, row


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--only", help="run only sources whose name contains this text (test mode, writes nothing)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--offline", action="store_true", help="don't contact any job sites; rebuild from claude_found.json and saved data")
    args = ap.parse_args(argv)

    now = datetime.now(TZ)
    today = now.date()
    settings = load_yaml(CONFIG / "settings.yaml")
    comp_cfg = load_yaml(CONFIG / "companies.yaml")
    companies = (comp_cfg.get("companies") or []) + (comp_cfg.get("discovered") or [])
    cache = load_json(CONFIG / "ats_cache.json", {})

    if args.offline:
        manual = [{"name": c["name"], "url": c.get("manual_url") or c.get("careers_url", ""), "sector": c.get("sector", ""),
                   "why": "Can't be read automatically"} for c in companies if c.get("manual")]
        status_rows = [{"name": c["name"], "type": c.get("type", "auto-detect"), "status": "skipped", "found": 0, "kept": 0,
                        "message": "Not checked in this offline preview. The daily GitHub run checks it."}
                       for c in companies if not c.get("manual") and not c.get("disabled")]
        runnable = []
    else:
        runnable, manual, status_rows = resolve_sources(settings, companies, cache, today, args.workers)
        runnable += AGGREGATORS
    if args.only:
        runnable = [s for s in runnable if args.only.lower() in s["name"].lower()]
        status_rows = []
    print(f"Checking {len(runnable)} sources…", flush=True)

    records, details, reasons = [], {}, {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_source, s, settings, today) for s in runnable]
        for f in as_completed(futs):
            src, raws, row = f.result()
            for raw in raws:
                rec, extra = normalize(raw, src, settings, today)
                if rec is None:
                    reasons[extra] = reasons.get(extra, 0) + 1
                    continue
                records.append(rec)
                details[rec["id"]] = extra
                row["kept"] += 1
            status_rows.append(row)
            print(f"  {row['status']:>14}  {row['name']}: {row['found']} found, {row['kept']} kept {row['message'][:90]}", flush=True)

    # Postings the weekly Claude discovery task found by web search
    claude_src = {"name": "Claude weekly discovery", "type": "claude", "sector": ""}
    claude_found = load_json(DATA / "claude_found.json", [])
    kept_c = 0
    for cf in claude_found:
        try:
            if cf.get("expires") and date.fromisoformat(cf["expires"]) < today:
                continue
            raw = {"ext_id": cf.get("url"), "title": cf["title"], "url": cf["url"], "locations": [cf.get("location", "")],
                   "description": cf.get("description", ""), "posted": cf.get("posted"), "company": cf.get("company"), "pay_text": cf.get("pay", "")}
            rec, extra = normalize(raw, {**claude_src, "sector": cf.get("sector", "")}, settings, today, trusted=True)
            if not rec:
                print(f"  Claude-found posting skipped ({extra}): {cf.get('title')}")
            if rec:
                if cf.get("deadline"):
                    rec["deadline"] = cf["deadline"]
                records.append(rec)
                details[rec["id"]] = extra
                kept_c += 1
        except Exception as e:
            print("claude_found entry skipped:", e)
    status_rows.append({"name": "Claude weekly discovery", "type": "claude", "status": "ok", "found": len(claude_found), "kept": kept_c, "message": ""})

    records = dedupe(records)
    print(f"Kept {len(records)} listings. Skipped: {reasons}")
    if args.only:
        for r in sorted(records, key=lambda r: -score(r, settings, today)):
            print(f"  {score(r, settings, today):>3}  {r['title']} | {r['company']} | {r.get('city')} {r.get('km')} km | term {r['term']} | start {r['start']} | pay {r['pay']}")
        return 0

    # ---- merge with history
    old = load_json(DATA / "jobs.json", {"jobs": []}).get("jobs", [])
    first_run = not old
    ok_sources = {r["name"] for r in status_rows if r["status"] == "ok"}
    jobs = merge(old, records, ok_sources, today, settings.get("close_after_missed_runs", 3))

    summaries = load_json(DATA / "summaries.json", {})
    for j in jobs:
        s = summaries.get(j["id"])
        if s:
            j["summary"] = s.get("summary")
            j["fit_notes"] = s.get("fit_notes")
            j["summary_date"] = s.get("date")
        j["score"] = score(j, settings, today)

    old_details = load_json(DATA / "details.json", {})
    old_details.update(details)
    live_ids = {j["id"] for j in jobs}
    details_out = {k: v for k, v in old_details.items() if k in live_ids}

    jobs.sort(key=lambda j: (not j.get("active", True), -j["score"]))
    okc = sum(1 for r in status_rows if r["status"] == "ok")
    failc = sum(1 for r in status_rows if r["status"] in ("error", "blocked"))
    next_run = (now + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)
    meta = {
        "last_run": now.isoformat(timespec="minutes"),
        "run_label": now.strftime("%a %b %-d, %Y · %-I:%M %p"),
        "next_run": next_run.isoformat(timespec="minutes"),
        "home": settings["home"],
        "priority_radius_km": settings["priority_radius_km"],
        "keywords": list(settings["keywords"].keys()),
        "earliest_start": settings["earliest_start"],
        "weights": settings["weights"],
        "source_counts": {"ok": okc, "failed": failc, "total": len(status_rows)},
        "skipped": reasons,
        "first_run": first_run,
    }
    sources_out = sorted(status_rows, key=lambda r: ({"ok": 0, "not-configured": 1, "blocked": 2, "error": 3, "undetected": 4}.get(r["status"], 5), r["name"]))
    save_json(DATA / "jobs.json", {"generated": meta["last_run"], "jobs": jobs})
    save_json(DATA / "details.json", details_out)
    save_json(DATA / "meta.json", meta)
    save_json(DATA / "sources.json", {"sources": sources_out, "manual": manual})
    save_json(CONFIG / "ats_cache.json", cache)
    if not (DATA / "summaries.json").exists():
        save_json(DATA / "summaries.json", {})
    if not (DATA / "claude_found.json").exists():
        save_json(DATA / "claude_found.json", [])

    # ---- email
    if args.no_email:
        return 0
    active = [j for j in jobs if j.get("active", True)]
    for j in active:
        j["_score"] = j["score"]
    new = [j for j in active if j.get("is_new")][: settings["email"]["max_items"]]
    soon = [j for j in active if j.get("deadline") and 0 <= (date.fromisoformat(j["deadline"]) - today).days <= 7][:10]
    roundup = today.weekday() == settings["email"].get("weekly_roundup_weekday", 0)
    top = active[:10] if roundup else []
    try:
        if new or roundup or settings["email"].get("send_when_nothing_new"):
            subject, body = emailer.build(new, soon, top, meta, settings["site_url"], first_run=first_run)
            print("Email:", emailer.send(subject, body))
        else:
            print("Email: nothing new today, no email sent")
        pct = 100 * failc / max(1, okc + failc)
        if pct > settings["email"].get("alert_if_sources_failing_pct", 50):
            print("Alert:", emailer.send_alert("Co-op Scout needs attention",
                                                f"{failc} of {okc + failc} sources could not be read today. Open the website's 'Sources' section for details."))
    except Exception as e:
        print("Email failed:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
