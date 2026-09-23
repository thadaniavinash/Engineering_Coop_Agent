"""Build a demo copy of the website with made-up listings, run through the real pipeline.
    python -m tests.make_demo /tmp/demo-site
Used only for local testing; nothing here is published."""
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import yaml

from agent.pipeline import normalize, dedupe, merge, score

ROOT = Path(__file__).resolve().parent.parent
S = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text())
TODAY = date.today()

RAW = [
    ("Magna International", "Automotive", "Mechanical Engineering Co-op, Product Development (16 months)", "Aurora, Ontario, Canada",
     "16-month co-op starting May 2027. Seat structure design with SolidWorks and GD&T, prototype builds, manufacturing support. $24 - $28 per hour. Apply by November 14, 2026. On-site."),
    ("Multimatic", "Automotive", "Engineering Intern, Vehicle Systems (12-16 months)", "Markham, ON",
     "12 to 16 month internship beginning May 2027. Suspension systems design, CAD packaging (CATIA or SolidWorks), test rigs. $23 to $27 per hour."),
    ("Honda Canada", "Automotive", "Manufacturing Engineering Co-op (12 months)", "Alliston, Ontario",
     "12 month co-op, start May 2027. Weld and paint line process improvement, manufacturing systems."),
    ("Ontario Power Generation", "Nuclear & energy", "Engineering Co-op Student - Mechanical", "Pickering, ON, CA",
     "Station mechanical systems: pumps, valves, heat exchangers. Work term begins May 2027. Must obtain site access security clearance. $26 - $30 per hour. Closing date: October 30, 2026."),
    ("Celestica", "Electronics manufacturing", "Mechanical Engineering Intern - Hardware Design", "Toronto, ON",
     "Enclosure and sheet-metal design using SolidWorks for data-centre hardware, design for manufacturing."),
    ("RTX (Pratt & Whitney Canada, Collins)", "Aerospace", "Mechanical Design Engineering Intern (12 months)", "Mississauga, Ontario, Canada",
     "12-month internship starting May 2027, engine component design, NX and ANSYS, systems thinking. Controlled Goods eligibility required. $25 - $29 per hour."),
    ("Honeywell", "Aerospace & automation", "Systems Engineering Co-op (16 months)", "Mississauga, ON, Canada",
     "16 month co-op beginning September 2027. Requirements and verification of avionics mechanical systems design. Hybrid."),
    ("Martinrea International", "Automotive", "Process Engineering Co-op (12 months)", "Vaughan, Ontario",
     "12 month co-op starting January 2027. Stamping and assembly process engineering, manufacturing."),
    ("Bruce Power", "Nuclear & energy", "Mechanical Engineering Co-op (16 months)", "Tiverton, Ontario",
     "16-month mechanical engineering co-op, start May 2027, Major Component Replacement systems. $27 - $31 per hour. Security clearance required."),
    ("Procter & Gamble", "Consumer goods", "Engineering Co-op - Manufacturing (16 months)", "Belleville, Ontario, Canada",
     "16 month engineering co-op, start Summer 2027, packaging equipment reliability, manufacturing systems."),
    ("AECOM", "Engineering consulting", "Mechanical Engineering Co-op, Building Systems", "Markham, ON",
     "12-month co-op beginning May 2027: HVAC design and Revit mechanical systems drawings. $21 - $24 per hour. Hybrid."),
    ("Husky Technologies", "Industrial machinery", "Mechanical Design Intern, Hot Runner Systems", "Bolton, Ontario",
     "16 month internship: hot runner design with SolidWorks, tolerance stack-ups, manufacturing drawings."),
    ("General Motors Canada", "Automotive", "Vehicle Systems Engineering Intern", "Markham, Ontario, Canada",
     "EV systems validation and mechanical design support at the Canadian Technical Centre."),
    ("Toyota Canada (co-op site)", "Automotive", "Production Engineering Co-op (4 months)", "Cambridge, Ontario",
     "4-month summer co-op, manufacturing engineering, start May 2027."),
    ("Adzuna (job aggregator)", "", "Mechanical Design Co-op (12-16 months)", "Georgetown, ON",
     "SolidWorks-heavy injection-moulding component design, 12 or 16 months, May 2027 start."),
    ("Magna International", "Automotive", "Mechanical Engineering Co-op (8 months)", "Detroit, MI", "US role"),
    ("Celestica", "Electronics manufacturing", "Payroll Co-op", "Toronto, ON", "Payroll"),
]


def main(out):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "docs", out)
    recs, details = [], {}
    for i, (co, sector, title, loc, desc) in enumerate(RAW):
        raw = {"ext_id": str(i), "title": title, "url": f"https://example.com/job/{i}", "locations": [loc], "description": desc,
               "posted": date.fromordinal(TODAY.toordinal() - (i * 2) % 20).isoformat(), "company": "Mold-Masters" if "Adzuna" in co else None, "pay_text": ""}
        r, d = normalize(raw, {"name": co, "sector": sector, "type": "adzuna" if "Adzuna" in co else "workday"}, S, TODAY)
        if r:
            recs.append(r)
            details[r["id"]] = d
    old = [dict(r, first_seen="2026-09-01") for r in recs[3:]]  # pretend most were seen before
    jobs = merge(old, dedupe(recs), set(), TODAY, 3)
    for j in jobs:
        j["score"] = score(j, S, TODAY)
    jobs[0]["summary"] = "Seat-structure design from concept to prototype. Heavy SolidWorks and GD&T; you'd own drawing packages and fixture design."
    jobs[0]["fit_notes"] = "Strong fit: 16 months, May 2027, 8 km from home."
    jobs[0]["summary_date"] = TODAY.isoformat()
    meta = {"last_run": f"{TODAY.isoformat()}T07:02-04:00", "run_label": "demo", "next_run": f"{TODAY.isoformat()}T07:00-04:00",
            "home": S["home"], "priority_radius_km": 50, "keywords": list(S["keywords"]), "earliest_start": S["earliest_start"],
            "weights": S["weights"], "source_counts": {"ok": 40, "failed": 3, "total": 45}}
    d = out / "data"
    d.mkdir(exist_ok=True)
    (d / "jobs.json").write_text(json.dumps({"jobs": jobs}))
    (d / "details.json").write_text(json.dumps(details))
    (d / "meta.json").write_text(json.dumps(meta))
    (d / "summaries.json").write_text("{}")
    (d / "sources.json").write_text(json.dumps({"sources": [
        {"name": "Magna International", "status": "ok", "found": 12, "kept": 2, "message": "", "seconds": 14.2},
        {"name": "Tesla", "status": "blocked", "found": 0, "kept": 0, "message": "site refused access (HTTP 403)"},
        {"name": "Adzuna (job aggregator)", "status": "not-configured", "found": 0, "kept": 0, "message": "add ADZUNA_APP_ID and ADZUNA_APP_KEY secrets to turn this on (free)"},
        {"name": "Linamar", "status": "undetected", "found": 0, "kept": 0, "message": "Couldn't tell which careers system this site uses."}],
        "manual": [{"name": "TMU Co-op portal (student login)", "url": "https://www.torontomu.ca/", "sector": "School", "why": "Can't be read automatically"}]}))
    print(f"{len(jobs)} demo listings written to {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/demo-site")
