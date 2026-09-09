"""
Adzuna adapter — free job API with strong India coverage plus global.

Needs ADZUNA_APP_ID and ADZUNA_APP_KEY in .env (free signup at
https://developer.adzuna.com/). Auto-skipped until both are present.
"""

import os

from .base import Source, get_json, strip_html
from .config import SEARCH_QUERIES


# Countries to search. "in" = India; add global-remote coverage via gb/us.
COUNTRIES = ["in", "gb", "us"]

RESULTS_PER_PAGE = 25


class AdzunaSource(Source):
    name = "adzuna"

    def is_configured(self):
        return bool(os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY"))

    def search(self, queries=None, locations=None, remote=True):
        app_id = os.getenv("ADZUNA_APP_ID")
        app_key = os.getenv("ADZUNA_APP_KEY")
        if not (app_id and app_key):
            return []

        queries = queries or SEARCH_QUERIES
        jobs = []
        seen = set()

        for country in COUNTRIES:
            # For non-India countries we only want remote roles.
            country_queries = (
                queries if country == "in"
                else [f"{q} remote" for q in queries]
            )

            for query in country_queries:
                url = (
                    f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
                )
                try:
                    data = get_json(url, params={
                        "app_id": app_id,
                        "app_key": app_key,
                        "what": query,
                        "results_per_page": RESULTS_PER_PAGE,
                        "content-type": "application/json",
                    })
                except Exception as error:  # noqa: BLE001
                    self.log(f"ERROR {query!r} [{country}]: {error}")
                    continue

                for job in data.get("results", []):
                    link = job.get("redirect_url")
                    if link and link in seen:
                        continue
                    if link:
                        seen.add(link)

                    company = (job.get("company") or {}).get("display_name")
                    location = (job.get("location") or {}).get("display_name")
                    desc = strip_html(job.get("description"))

                    jobs.append(self.normalize(
                        title=job.get("title"),
                        company=company,
                        url=link,
                        location=location,
                        job_type=job.get("contract_time"),
                        snippet=desc[:400],
                        description=desc,
                        posted=job.get("created"),
                        remote=(country != "in"),
                        origin=f"adzuna-{country}",
                        query=query,
                    ))

        return jobs
