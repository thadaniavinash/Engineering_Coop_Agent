"""Adapter tests against canned responses shaped like each careers system's real output.
(The live check happens on the first GitHub Actions run; see the website's Sources section.)"""
import json
from datetime import date
from pathlib import Path

import yaml

from agent.sources import workday, successfactors, phenom, oracle, boards, aggregators
from agent.sources.common import Ctx
from agent.detect import detect_from_html
from agent.pipeline import normalize, dedupe, merge, score

S = yaml.safe_load((Path(__file__).parent.parent / "config" / "settings.yaml").read_text())
S["search_terms"] = ["co-op"]
S["aggregator_queries"] = ["mechanical engineering co-op"]
TODAY = date(2026, 9, 23)


class Resp:
    def __init__(self, text="", data=None, url=""):
        self.text, self._data, self.url = text, data, url

    def json(self):
        return self._data


class FakeHttp:
    """Routes URLs to canned responses by substring."""
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _find(self, url):
        self.calls.append(url)
        for key, val in self.routes.items():
            if key in url:
                return val
        raise AssertionError(f"unexpected URL {url}")

    def get(self, url, **kw):
        v = self._find(url)
        return v if isinstance(v, Resp) else Resp(text=v if isinstance(v, str) else "", data=v, url=url)

    def get_json(self, url, **kw):
        v = self._find(url)
        return v._data if isinstance(v, Resp) else v

    def post_json(self, url, payload, **kw):
        return self.get_json(url)


def ctx(routes):
    return Ctx(http=FakeHttp(routes), settings=S, today=TODAY)


def test_workday():
    routes = {
        "/jobs": {"total": 3, "jobPostings": [
            {"title": "Mechanical Engineering Co-op (16 months)", "externalPath": "/job/Aurora/ME-Coop_R1", "locationsText": "Aurora, Ontario, Canada", "postedOn": "Posted 2 Days Ago"},
            {"title": "Mechanical Engineering Co-op", "externalPath": "/job/Detroit/ME_R2", "locationsText": "Detroit, MI", "postedOn": "Posted Today"},
            {"title": "Senior Mechanical Engineer", "externalPath": "/job/Aurora/Sr_R3", "locationsText": "Aurora, Ontario, Canada", "postedOn": "Posted Today"}]},
        "/job/Aurora/ME-Coop_R1": {"jobPostingInfo": {"title": "Mechanical Engineering Co-op (16 months)", "jobReqId": "R1",
            "jobDescription": "<p>16-month co-op starting May 2027. SolidWorks, GD&amp;T, design of seating systems. $24 - $28 per hour. Apply by October 31, 2026.</p>",
            "location": "Aurora, Ontario", "country": {"descriptor": "Canada"}, "startDate": "2026-09-21",
            "externalUrl": "https://magna.wd3.myworkdayjobs.com/Magna/job/Aurora/ME-Coop_R1"}},
    }
    out = workday.fetch({"host": "magna.wd3.myworkdayjobs.com", "tenant": "magna", "site": "Magna"}, ctx(routes))
    assert len(out) == 1
    rec, desc = normalize(out[0], {"name": "Magna International", "sector": "Automotive", "type": "workday"}, S, TODAY)
    assert rec["term"] == "16" and rec["start"] == "2027-05" and rec["pay"] == [24.0, 28.0]
    assert rec["city"] == "Aurora" and rec["km"] < 10 and rec["deadline"] == "2026-10-31"
    assert "SolidWorks" in rec["kw"] and "GD&T" in rec["skills"]


SF_SEARCH = """<table><tr class="data-row"><td><span class="jobTitle hidden-phone"><a class="jobTitle-link" href="/job/Pickering-Engineering-Co-op-Student-Mechanical-ON/1234567/">Engineering Co-op Student - Mechanical</a></span></td>
<td><span class="jobLocation">Pickering, ON, CA</span></td><td><span class="jobDate">Sep 19, 2026</span></td></tr>
<tr class="data-row"><td><a class="jobTitle-link" href="/job/Toronto-Payroll-Co-op/7654321/">Payroll Co-op</a></td><td><span class="jobLocation">Toronto, ON, CA</span></td></tr></table>"""
SF_JOB = """<html><body><span class="jobdescription"><p>Work term: 12 or 16 months beginning May 2027. Mechanical systems, pumps and valves.
Must obtain site access security clearance.</p></span></body></html>"""


def test_successfactors():
    out = successfactors.fetch({"base": "https://jobs.opg.com"}, ctx({"/search/": SF_SEARCH, "/job/Pickering": SF_JOB}))
    assert len(out) == 1 and out[0]["posted"] == "2026-09-19"
    rec, _ = normalize(out[0], {"name": "OPG", "type": "successfactors"}, S, TODAY)
    assert rec["term"] == "12-16" and rec["citizen"] and rec["city"] == "Pickering"


PH = 'phApp.ddo = %s; phApp.experimentData = {};'


def test_phenom():
    search = PH % json.dumps({"eagerLoadRefineSearch": {"data": {"jobs": [
        {"jobId": "R123", "title": "Engineering Co-Op - Manufacturing (16 months)", "city": "Belleville", "state": "Ontario", "country": "Canada",
         "postedDate": "2026-09-14T00:00:00.000+0000", "descriptionTeaser": "Manufacturing line reliability"}]}}})
    detail = PH % json.dumps({"jobDetail": {"data": {"job": {"description": "<p>16-month engineering co-op, manufacturing systems, start May 2027.</p>"}}}})
    out = phenom.fetch({"base": "https://www.pgcareers.com", "locale": "global/en"}, ctx({"search-results": search, "/job/R123": detail}))
    rec, _ = normalize(out[0], {"name": "P&G", "type": "phenom"}, S, TODAY)
    assert rec["term"] == "16" and rec["city"] == "Belleville" and rec["posted"] == "2026-09-14"


def test_oracle():
    lst = {"items": [{"requisitionList": [{"Id": "999", "Title": "Mechanical Engineering Co-op", "PostedDate": "2026-09-16",
                                          "PrimaryLocation": "Mississauga, ON, Canada", "ShortDescriptionStr": "co-op"}]}]}
    det = {"items": [{"ExternalDescriptionStr": "<p>16 month co-op beginning September 2027, systems engineering and design</p>"}]}
    out = oracle.fetch({"host": "x.oraclecloud.com", "site_numbers": ["Honeywell"], "location_id": "1",
                        "job_url": "https://careers.honeywell.com/en/sites/Honeywell/job/{id}"},
                       ctx({"recruitingCEJobRequisitionDetails": det, "recruitingCEJobRequisitions": lst}))
    assert out[0]["url"].endswith("/job/999")
    rec, _ = normalize(out[0], {"name": "Honeywell", "type": "oracle"}, S, TODAY)
    assert rec["start"] == "2027-09" and rec["term"] == "16"


def test_greenhouse_lever_smartrecruiters():
    gh = {"jobs": [{"id": 1, "title": "Mechanical Design Intern", "absolute_url": "https://x/1", "location": {"name": "Toronto, Ontario"},
                    "content": "&lt;p&gt;12-month mechanical design internship using SolidWorks&lt;/p&gt;", "updated_at": "2026-09-01T00:00:00Z"}]}
    out = boards.greenhouse({"board": "acme"}, ctx({"greenhouse.io": gh}))
    assert out and normalize(out[0], {"name": "Acme", "type": "greenhouse"}, S, TODAY)[0]["term"] == "12"
    lv = [{"id": "a", "text": "Mechanical Engineering Co-op", "hostedUrl": "https://jobs.lever.co/k/a",
           "categories": {"location": "Toronto, ON", "commitment": "Co-op 16 months"}, "descriptionPlain": "Design satellite systems", "createdAt": 1726000000000}]
    out = boards.lever({"company_id": "k"}, ctx({"lever.co": lv}))
    assert normalize(out[0], {"name": "Kepler", "type": "lever"}, S, TODAY)[0]["term"] == "16"
    sr_list = {"content": [{"id": "p1", "name": "Mechanical Engineering Co-op Student", "location": {"city": "Markham", "region": "ON", "country": "ca"}, "releasedDate": "2026-09-20T00:00:00Z"}]}
    sr_det = {"jobAd": {"sections": {"jobDescription": {"text": "<p>HVAC mechanical design, 12 months</p>"}}}}
    out = boards.smartrecruiters({"company_id": "AECOM2"}, ctx({"postings/p1": sr_det, "postings?": sr_list}))
    rec = normalize(out[0], {"name": "AECOM", "type": "smartrecruiters"}, S, TODAY)[0]
    assert rec["city"] == "Markham" and rec["term"] == "12"


def test_jobbank_and_directemployers():
    jb = """<article><a class="resultJobItem" href="/jobsearch/jobposting/4455;jsessionid=x"><span class="noctitle">mechanical engineering co-op student</span>
    <ul><li class="date">September 18, 2026</li><li class="business">Acme Tooling Inc.</li><li class="location"><span>Location</span> Concord (ON)</li>
    <li class="salary">$23.00 hourly</li></ul></a></article>"""
    out = aggregators.jobbank({}, ctx({"jobsearch?": jb, "jobposting/4455": "<main>16 month co-op, SolidWorks tooling design</main>"}))
    rec = normalize(out[0], {"name": "Job Bank Canada", "type": "jobbank"}, S, TODAY)[0]
    assert rec["company"] == "Acme Tooling Inc." and rec["city"] == "Concord" and rec["term"] == "16"
    de = """<ul><li><a href="/toronto-on/mechanical-engineering-co-op/ABC123/job/">Mechanical Engineering Co-op</a><span class="location">Toronto, ON</span></li></ul>"""
    out = boards.directemployers({"base": "https://stantec.jobs"}, ctx({"/jobs/?q=": de, "ABC123": "<div id='job_description'>12-month co-op, building systems design</div>"}))
    assert normalize(out[0], {"name": "Stantec", "type": "directemployers"}, S, TODAY)[0]["term"] == "12"


def test_detect():
    assert detect_from_html('<a href="https://acme.wd3.myworkdayjobs.com/en-US/Acme_Careers">Jobs</a>', "https://acme.com")["site"] == "Acme_Careers"
    assert detect_from_html('<iframe src="https://boards.greenhouse.io/embed/job_board?for=ecobee">', "x")["board"] == "ecobee"
    assert detect_from_html('<a href="https://jobs.lever.co/kepler">', "x")["company_id"] == "kepler"
    assert detect_from_html('<link href="https://rmkcdn.successfactors.com/a.css">', "https://jobs.acme.com/go/x")["base"] == "https://jobs.acme.com"
    assert detect_from_html("<p>nothing</p>", "x") is None


def test_merge_and_dedupe():
    a = {"id": "1", "title": "ME Co-op", "company": "Acme", "city": "Toronto", "source": "Acme", "source_type": "workday"}
    b = {"id": "2", "title": "ME Co-op", "company": "Acme Inc", "city": "Toronto", "source": "Adzuna", "source_type": "adzuna"}
    assert [r["id"] for r in dedupe([b, a])] == ["1"]
    old = [{"id": "x", "source": "Acme", "first_seen": "2026-09-01", "last_seen": "2026-09-22", "summary": "hi", "missed": 2, "active": True}]
    new = [{"id": "y", "source": "Acme"}]
    out = {r["id"]: r for r in merge(old, new, {"Acme"}, TODAY, 3)}
    assert out["y"]["is_new"] and not out["x"]["active"]
    out = {r["id"]: r for r in merge(old, [{"id": "x", "source": "Acme"}], {"Acme"}, TODAY, 3)}
    assert out["x"]["summary"] == "hi" and out["x"]["first_seen"] == "2026-09-01" and not out["x"]["is_new"]


def test_score_order():
    near = {"match": 0.9, "km": 8, "term": "16", "start": "2027-05", "pay": [24, 28], "posted": "2026-09-22"}
    far = {"match": 0.5, "km": 190, "term": "unclear", "start": "unclear", "pay": None, "posted": "2026-08-01"}
    assert score(near, S, TODAY) > 85 > score(far, S, TODAY)
