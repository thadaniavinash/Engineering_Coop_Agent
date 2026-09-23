# Co-op Scout

An automated search for **12- and 16-month mechanical engineering co-op roles in Ontario** that start in **May 2027 or later**, ranked by fit and distance from Newmarket.

- **Website:** https://thadaniavinash.github.io/Engineering_Coop_Agent/
- **Runs:** every morning at about 7 a.m. Toronto time, on GitHub's free servers (GitHub Actions). No computer needs to stay on.
- **Email:** new listings go to the addresses in the `EMAIL_TO` secret, and a "Top 10" roundup goes out every Monday.
- **Claude:** a weekly Claude task writes short summaries and searches the web for employers that aren't on the list yet.
- **Cost:** $0.

## How it works

```
 every morning (GitHub Actions)                                  weekly (Claude scheduled task)
 ┌──────────────────────────────────────────────┐               ┌──────────────────────────────────┐
 │ 1. Read ~70 company careers sites + 3 job    │               │ • Summarise new listings          │
 │    aggregators (config/companies.yaml)       │               │ • Web-search for more postings    │
 │ 2. Keep student roles in Ontario that match  │   docs/data   │   and employers                   │
 │    the keywords (config/settings.yaml)       │ ◄───────────► │ • Fix sites the agent can't read  │
 │ 3. Pull out term, start, pay, deadline,      │   (JSON)      └──────────────────────────────────┘
 │    distance from Newmarket                   │
 │ 4. Save to docs/data/*.json → website updates│
 │ 5. Email anything new                        │
 └──────────────────────────────────────────────┘
```

| Folder / file | What it is |
|---|---|
| `config/settings.yaml` | Keywords, home location, start date, ranking weights, email options. **Edit this to change the search.** |
| `config/companies.yaml` | The employers and job boards that are checked. Add a company by adding a line. |
| `agent/` | The Python search agent. |
| `docs/` | The website (GitHub Pages serves this folder). `docs/data/` is rewritten on every run. |
| `.github/workflows/daily.yml` | The daily schedule. |
| `claude/WEEKLY_TASK.md` | The instructions the weekly Claude task follows. |
| `tests/` | Automated tests (`python -m pytest`). |

## Common changes

- **Add a company:** edit `config/companies.yaml` (pencil icon on GitHub) and add a line like
  `- {name: Acme Robotics, sector: Robotics, careers_url: "https://acme.com/careers"}`.
  The agent works out the careers system on the next run. If it can't, the company appears under "Check by hand" on the website.
- **Change keywords or the start date:** edit `config/settings.yaml`.
- **Run it now:** open the **Actions** tab, choose **Daily co-op search**, then **Run workflow**.
- **Pause it:** Actions tab → Daily co-op search → "…" menu → **Disable workflow**.

## Running it on your own computer

You'll need Python 3.10 or newer.

```bash
pip install -r requirements.txt
python -m agent.run --no-email             # full search, same as the daily run (about 10–20 min)
python -m agent.run --offline --no-email   # quick rebuild from saved data, no web requests
cd docs && python -m http.server 8000      # then open http://localhost:8000
```

## Limitations

- Some sites (Tesla, LinkedIn, Indeed, the TMU co-op portal) block automated tools or need a login. They're listed under **Check by hand**.
- Many postings don't state the term length or start date. Those are kept and marked **Needs check**.
- Distances are straight-line from Newmarket.
- Shortlist and status marks are saved in the browser you use. **Export CSV** saves a copy.
- The agent honours each site's robots.txt, sends only a few requests a day to each site, and identifies itself.
- GitHub pauses scheduled workflows in repositories with no activity for 60 days. The daily data commits normally keep it active. If the workflow is ever paused, re-enable it on the Actions tab.
