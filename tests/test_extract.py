from datetime import date
import yaml
from pathlib import Path

from agent import extract as X
from agent.geo import classify, combine

S = yaml.safe_load((Path(__file__).parent.parent / "config" / "settings.yaml").read_text())


def test_term_labels():
    cases = {
        "This is a 16-month co-op starting May 2027": "16",
        "12 month internship": "12",
        "We offer 12-16 month placements": "12-16",
        "12 or 16 months": "12-16",
        "8, 12 or 16 month work terms": "12-16",
        "a sixteen month term": "16",
        "PEY Co-op student": "12-16",
        "4-month summer co-op": "other",
        "8 month co-op (Jan-Aug)": "other",
        "Join our team as a co-op student": "unclear",
        "3-6 months of experience with CAD": "unclear",
        "one-year internship": "12",
    }
    for text, want in cases.items():
        assert X.term_label(X.term_months(text)) == want, text


def test_start_dates():
    assert X.start_date("Start date: May 2027 for 16 months", 2026) == "2027-05"
    assert X.start_date("Summer 2027 work term", 2026) == "2027-05"
    assert X.start_date("Fall 2027 (September) start", 2026) == "2027-09"
    assert X.start_date("Apply by October 15, 2026. Starts January 2027.", 2026) == "2027-01"
    assert X.start_date("No dates here", 2026) == "unclear"


def test_pay():
    assert X.pay_range("Pay: $24.50 - $28.00 per hour") == [24.5, 28.0]
    assert X.pay_range("$22/hr to $26/hr") is None or X.pay_range("$22 to $26 per hour") == [22.0, 26.0]
    assert X.pay_range("$22 to $26 per hour") == [22.0, 26.0]
    lo, hi = X.pay_range("Salary range: $45,000 - $55,000 annually")
    assert 21 < lo < 22 and 26 < hi < 27
    assert X.pay_range("$50K–$60K") is not None
    assert X.pay_range("We have 5,000 employees") is None


def test_deadline_mode_clearance():
    assert X.deadline("Please apply by November 3, 2026 via the portal") == "2026-11-03"
    assert X.deadline("Closing date: 2026-10-31") == "2026-10-31"
    assert X.work_mode("This is a hybrid role") == "Hybrid"
    assert X.needs_clearance("Must be eligible for Controlled Goods registration")


def test_relevance():
    ok, _ = X.is_relevant("Mechanical Engineering Co-op (16 months)", "SolidWorks design", S)
    assert ok
    ok, why = X.is_relevant("Software Developer Co-op", "Python and design systems", S)
    assert not ok and why == "different discipline"
    ok, why = X.is_relevant("Mechanical Engineer", "Senior role, 10 years", S)
    assert not ok and why == "not a student role"
    ok, _ = X.is_relevant("Engineering Intern, Vehicle Systems", "engineering design of systems", S)
    assert ok
    ok, _ = X.is_relevant("Electrical & Mechanical Co-op", "manufacturing", S)
    assert ok
    ok, why = X.is_relevant("HR Co-op Student", "engineering", S)
    assert not ok


def test_keywords():
    hits = X.keyword_hits("Uses SolidWorks for mechanical design of manufacturing systems", S["keywords"])
    assert set(hits) == {"Mechanical Engineering", "SolidWorks", "Design", "Systems", "Manufacturing"}


def test_geo():
    g = classify("Aurora, Ontario, Canada")
    assert g["region"] == "ontario" and g["km"] <= 10
    assert classify("Mississauga, ON")["km"] in range(50, 62)
    assert classify("Longueuil, Quebec, Canada")["region"] == "other-canada"
    assert classify("London, England")["region"] == "foreign"
    assert classify("London, ON")["region"] == "ontario"
    assert classify("Cambridge, MA")["region"] == "foreign"
    assert classify("New York, NY")["region"] == "foreign"
    assert classify("Canada")["region"] == "canada-unknown"
    assert classify("ELC01-Midland-Ontario-Canada-450-Leitz-Road")["city"] == "Midland"
    best = combine(["Montreal, QC", "Mississauga, ON", "Toronto, ON"])
    assert best["city"] == "Toronto"


def test_workday_posted():
    assert X.workday_posted("Posted 3 Days Ago", date(2026, 9, 23)) == "2026-09-20"
    assert X.workday_posted("Posted Today", date(2026, 9, 23)) == "2026-09-23"
