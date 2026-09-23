"""A polite HTTP client: identifies itself, honours robots.txt, waits between requests
to the same site, and retries briefly on transient errors."""
from __future__ import annotations
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

UA = ("Mozilla/5.0 (compatible; EngineeringCoopAgent/1.0; personal co-op job search; "
      "+https://github.com/thadaniavinash/Engineering_Coop_Agent)")
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0 Safari/537.36 EngineeringCoopAgent/1.0")


class Blocked(Exception):
    """Raised when a site refuses us (robots.txt, 401/403, bot wall)."""


class Http:
    def __init__(self, delay: float = 1.0, timeout: float = 25.0):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": BROWSER_UA, "Accept-Language": "en-CA,en;q=0.9"})
        self.delay = delay
        self.timeout = timeout
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.requests_made = 0

    # -- robots.txt --------------------------------------------------------
    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.s.get(root + "/robots.txt", timeout=10)
                if r.status_code == 200 and "html" not in r.headers.get("content-type", "").lower():
                    rp.parse(r.text.splitlines())
                    self._robots[root] = rp
                else:
                    self._robots[root] = None  # no robots.txt -> allowed
            except requests.RequestException:
                self._robots[root] = None
        rp = self._robots[root]
        return True if rp is None else rp.can_fetch("EngineeringCoopAgent", url)

    # -- requests ----------------------------------------------------------
    def _wait(self, url: str):
        host = urlparse(url).netloc
        last = self._last.get(host, 0)
        gap = time.time() - last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last[host] = time.time()

    def request(self, method: str, url: str, check_robots: bool = True, **kw) -> requests.Response:
        if check_robots and not self.allowed(url):
            raise Blocked(f"robots.txt asks automated tools not to read {urlparse(url).path}")
        kw.setdefault("timeout", self.timeout)
        err = None
        for attempt in range(3):
            self._wait(url)
            try:
                r = self.s.request(method, url, **kw)
                self.requests_made += 1
            except requests.RequestException as e:
                err = e
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code in (401, 403):
                raise Blocked(f"site refused access (HTTP {r.status_code})")
            if r.status_code == 429 or r.status_code >= 500:
                err = requests.HTTPError(f"HTTP {r.status_code}")
                time.sleep(3 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        raise err or RuntimeError("request failed")

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def get_json(self, url, **kw):
        kw.setdefault("headers", {})["Accept"] = "application/json"
        return self.get(url, **kw).json()

    def post_json(self, url, payload, **kw):
        h = kw.setdefault("headers", {})
        h.update({"Accept": "application/json", "Content-Type": "application/json"})
        return self.post(url, json=payload, **kw).json()
