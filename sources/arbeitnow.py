"""
Arbeitnow adapter — free job board API (keyless), global + remote.
https://www.arbeitnow.com/api/job-board-api
"""

from .base import Source, get_json, strip_html, mentions_any


ENTRY = ["intern", "internship", "junior", "graduate", "trainee", "entry", "working student"]

DEV = [
    "developer", "engineer", "software", "full stack", "fullstack",
    "backend", "back-end", "frontend", "front-end", "python", "java",
    "node", "react", "devops", "sde",
]

MAX_PAGES = 3


class ArbeitnowSource(Source):
    name = "arbeitnow"

    def search(self, queries=None, locations=None, remote=True):
        jobs = []
        seen = set()

        for page in range(1, MAX_PAGES + 1):
            try:
                data = get_json(
                    "https://www.arbeitnow.com/api/job-board-api",
                    params={"page": page},
                )
            except Exception as error:  # noqa: BLE001
                self.log(f"ERROR page {page}: {error}")
                break

            rows = data.get("data") or []
            if not rows:
                break

            for job in rows:
                title = job.get("title") or ""
                tags = " ".join(job.get("tags") or [])
                types = " ".join(job.get("job_types") or [])
                haystack = f"{title} {tags} {types}"

                if not (mentions_any(haystack, ENTRY) and mentions_any(haystack, DEV)):
                    continue

                url = job.get("url")
                if url and url in seen:
                    continue
                if url:
                    seen.add(url)

                desc = strip_html(job.get("description"))

                jobs.append(self.normalize(
                    title=title,
                    company=job.get("company_name"),
                    url=url,
                    location=job.get("location"),
                    job_type=types,
                    snippet=desc[:400],
                    description=desc,
                    posted=str(job.get("created_at") or ""),
                    remote=bool(job.get("remote")),
                    origin="arbeitnow",
                    query="entry-level dev",
                ))

        return jobs
