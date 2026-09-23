from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date

from ..extract import term_hit
from ..geo import classify
from ..http import Http


@dataclass
class Ctx:
    http: Http
    settings: dict
    today: date
    log: list = field(default_factory=list)

    def title_ok(self, title: str) -> bool:
        """Cheap first pass on the title alone, before fetching the full posting."""
        t = title or ""
        if not term_hit(t, self.settings["student_terms"]):
            return False
        if term_hit(t, self.settings["exclude_title_terms"]) and "mechanical" not in t.lower():
            return False
        return True

    def location_maybe(self, loc_text: str) -> bool:
        """Keep anything that could be in Ontario (or where we can't tell yet)."""
        if not loc_text:
            return True
        if re.search(r"\d+\s+locations", loc_text, re.I):
            return True
        return classify(loc_text)["region"] in ("ontario", "canada-unknown", "unknown")


def job(ext_id, title, url, locations, description="", posted=None, company=None, pay_text="", extra=None) -> dict:
    return {"ext_id": str(ext_id), "title": (title or "").strip(), "url": url, "locations": [l for l in locations if l],
            "description": description or "", "posted": posted, "company": company, "pay_text": pay_text or "",
            "extra": extra or {}}
