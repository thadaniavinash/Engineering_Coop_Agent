# Weekly Claude task: summaries + discovery

This is the instruction the weekly Claude scheduled task follows. It runs every Sunday evening,
so fresh summaries are ready for Monday's roundup email.

---

You maintain the "Co-op Scout" job agent in the GitHub repository `thadaniavinash/Engineering_Coop_Agent`.
It helps a third-year TMU mechanical engineering student find **12- or 16-month co-op/internship roles in Ontario
starting May 2027 or later**, ideally near Newmarket, ON. Keywords: Mechanical Engineering, SolidWorks, Design, Systems, Manufacturing.

## 0. Get the repository
Clone with the access token provided at the end of this prompt:
`git clone https://x-access-token:<TOKEN>@github.com/thadaniavinash/Engineering_Coop_Agent.git repo && cd repo`
Configure git: user.name "Claude weekly task", user.email "noreply@anthropic.com".

## 1. Write summaries (docs/data/summaries.json)
- Read `docs/data/jobs.json` (listings) and `docs/data/details.json` (full descriptions keyed by listing id).
- For every listing with `"active": true` that has no entry in `summaries.json` yet (and any whose entry is older than 30 days),
  write an entry keyed by the listing `id`:
  `{"summary": "...", "fit_notes": "...", "date": "YYYY-MM-DD"}`
  - `summary`: 1–2 plain sentences (max ~40 words) saying what the student would actually do and which tools/skills matter.
  - `fit_notes`: one short sentence on fit for THIS student: term length (12/16 months?), start (May 2027 or later?),
    distance from Newmarket, and anything to check (e.g. "Term length not stated; confirm it's 12–16 months", "Needs security clearance").
  - Use only facts in the posting. If the description is empty, say so in fit_notes and keep the summary to the title's evident scope.
- Keep existing entries for listings that are still active; remove entries for ids no longer in jobs.json.

## 2. Discover more postings and employers
Use web search (at least 10 different searches), e.g.:
"16 month mechanical engineering co-op May 2027 Ontario", "12-16 month engineering internship 2027 Toronto",
"PEY co-op mechanical 2027 Markham OR Vaughan OR Mississauga", "mechanical engineering intern 16 months Ontario site:myworkdayjobs.com",
plus searches aimed at Southern Ontario manufacturers, automotive suppliers, aerospace, nuclear, robotics and medical-device companies.
- For each **specific, currently open posting** that fits (student role, Ontario, mechanical-related, not clearly a 4- or 8-month term,
  not clearly starting before May 2027) and is NOT already in jobs.json (compare company + title), append to `docs/data/claude_found.json`:
  `{"title", "company", "url", "location", "description" (2–4 factual sentences incl. any stated term/start/pay/deadline), "posted", "deadline", "sector", "expires": "<today + 45 days>"}`.
  Remove entries whose `expires` date has passed. Never invent details; only include what the posting says.
- For each **new employer** with a Southern Ontario presence that hires engineering co-ops and isn't in `config/companies.yaml`,
  add it under `discovered:` as `{name: ..., sector: ..., careers_url: "..."}`. If you can see it uses Workday, add
  `{name, sector, type: workday, host, tenant, site}` instead (from a URL like https://TENANT.wdN.myworkdayjobs.com/SITE).
  Add at most 10 employers per week.

## 3. Fix broken sources
Read `docs/data/sources.json`. For companies with status `undetected` or `error`, try to find their real careers system
by web search (Workday/Greenhouse/Lever/SmartRecruiters/SuccessFactors URLs) and update the entry in `config/companies.yaml`
to use `type:` settings. Don't touch entries with status `ok`. If a site simply can't be read, set `manual: true` and `manual_url:`.

## 4. Check and save
- Validate: `python -c "import json,yaml; json.load(open('docs/data/summaries.json')); json.load(open('docs/data/claude_found.json')); yaml.safe_load(open('config/companies.yaml'))"`
- If `pytest` is available, run `python -m pytest -q` and don't commit if it fails.
- Commit with message "Weekly Claude summaries & discovery (YYYY-MM-DD)", then `git pull --rebase` and `git push`.
- Finish with a short report: how many summaries were written, postings added, employers added, sources fixed.

Do not change any other files. Never put the access token in a file or commit.
