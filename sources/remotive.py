"""
Remotive adapter — free API of curated remote jobs (keyless).
https://remotive.com/api/remote-jobs
"""

from .base import Source, get_json, strip_html
from .config import ENTRY_TERMS


class RemotiveSource(Source):
    name = "remotive"

    def search(self, queries=None, locations=None, remote=True):
        jobs = []
        seen = set()

        # Query with a few entry-level terms inside the software category.
        for term in ["intern", "junior", "graduate"]:
            try:
                data = get_json(
                    "https://remotive.com/api/remote-jobs",
                    params={
                        "category": "software-dev",
                        "search": term,
                        "limit": 50,
                    },
                )
            except Exception as error:  # noqa: BLE001
                self.log(f"ERROR {term!r}: {error}")
                continue

            for job in data.get("jobs", []):
                url = job.get("url")
                if url and url in seen:
                    continue
                if url:
                    seen.add(url)

                desc = strip_html(job.get("description"))

                jobs.append(self.normalize(
                    title=job.get("title"),
                    company=job.get("company_name"),
                    url=url,
                    location=job.get("candidate_required_location"),
                    salary=job.get("salary"),
                    job_type=job.get("job_type"),
                    snippet=desc[:400],
                    description=desc,
                    posted=job.get("publication_date"),
                    remote=True,
                    origin="remotive",
                    query=term,
                ))

        return jobs
