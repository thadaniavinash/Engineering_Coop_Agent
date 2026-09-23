from . import workday, successfactors, phenom, oracle, boards, aggregators

ADAPTERS = {
    "workday": workday.fetch,
    "successfactors": successfactors.fetch,
    "phenom": phenom.fetch,
    "oracle": oracle.fetch,
    "greenhouse": boards.greenhouse,
    "lever": boards.lever,
    "smartrecruiters": boards.smartrecruiters,
    "directemployers": boards.directemployers,
    "tesla": boards.tesla,
    "adzuna": aggregators.adzuna,
    "jooble": aggregators.jooble,
    "jobbank": aggregators.jobbank,
}

AGGREGATORS = [
    {"name": "Adzuna (job aggregator)", "type": "adzuna", "sector": "Aggregator"},
    {"name": "Jooble (job aggregator)", "type": "jooble", "sector": "Aggregator"},
    {"name": "Job Bank Canada", "type": "jobbank", "sector": "Aggregator"},
]
