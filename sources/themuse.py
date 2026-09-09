"""
The Muse adapter — free public jobs API (keyless), supports an Internship level.
https://www.themuse.com/api/public/jobs
"""

from .base import Source, get_json, strip_html


CATEGORIES = ["Software Engineering", "Data Science", "Computer and IT"]

MAX_PAGES = 2


class TheMuseSource(Source):
    name = "themuse"

    def search(self, queries=None, locations=None, remote=True):
        jobs = []
        seen = set()

        for page in range(1, MAX_PAGES + 1):
            try:
                data = get_json(
                    "https://www.themuse.com/api/public/jobs",
                    params={
                        "category": CATEGORIES,
                        "level": "Internship",
                        "page": page,
                    },
                )
            except Exception as error:  # noqa: BLE001
                self.log(f"ERROR page {page}: {error}")
                break

            results = data.get("results") or []
            if not results:
                break

            for job in results:
                url = (job.get("refs") or {}).get("landing_page")
                if url and url in seen:
                    continue
                if url:
                    seen.add(url)

                company = (job.get("company") or {}).get("name")
                locs = ", ".join(
                    loc.get("name", "") for loc in (job.get("locations") or [])
                )
                desc = strip_html(job.get("contents"))

                jobs.append(self.normalize(
                    title=job.get("name"),
                    company=company,
                    url=url,
                    location=locs,
                    job_type=job.get("type"),
                    snippet=desc[:400],
                    description=desc,
                    posted=job.get("publication_date"),
                    remote="remote" in locs.lower(),
                    origin="themuse",
                    query="internship",
                ))

        return jobs
