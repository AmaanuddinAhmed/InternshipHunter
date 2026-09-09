"""
Jooble adapter — wraps the existing Jooble integration behind the Source API.

Jooble is an aggregator: it already indexes many boards (including LinkedIn /
Indeed / company pages), so it gives broad coverage from one legitimate API.
"""

import os

from .base import Source, post_json
from .config import SEARCH_QUERIES, LOCATIONS


class JoobleSource(Source):
    name = "jooble"

    def is_configured(self):
        return bool(os.getenv("JOOBLE_API_KEY"))

    def search(self, queries=None, locations=None, remote=True):
        api_key = os.getenv("JOOBLE_API_KEY")
        if not api_key:
            return []

        queries = queries or SEARCH_QUERIES
        locations = locations or LOCATIONS
        api_url = f"https://in.jooble.org/api/{api_key}"

        jobs = []
        seen = set()

        for query in queries:
            for location in locations:
                try:
                    data = post_json(
                        api_url,
                        json={
                            "keywords": query,
                            "location": location,
                            "page": 1,
                        },
                    )
                except Exception as error:  # noqa: BLE001
                    self.log(f"ERROR {query!r} @ {location!r}: {error}")
                    continue

                for job in data.get("jobs", []):
                    url = job.get("link")

                    if url and url in seen:
                        continue
                    if url:
                        seen.add(url)

                    is_remote = "remote" in (
                        f"{job.get('location', '')} {location}".lower()
                    )

                    jobs.append(self.normalize(
                        title=job.get("title"),
                        company=job.get("company"),
                        url=url,
                        location=job.get("location"),
                        salary=job.get("salary"),
                        job_type=job.get("type"),
                        snippet=job.get("snippet"),
                        posted=job.get("updated"),
                        origin=job.get("source"),
                        remote=is_remote,
                        query=query,
                    ))

        return jobs
