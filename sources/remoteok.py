"""
RemoteOK adapter — public JSON feed of remote jobs (keyless).
https://remoteok.com/api

The feed returns everything, so we keep only entry-level / dev-flavored roles
to avoid flooding the pipeline; pipeline.py filters again downstream.
"""

from .base import Source, get_json, strip_html, mentions_any


ENTRY = ["intern", "internship", "junior", "graduate", "trainee", "entry"]

DEV = [
    "developer", "engineer", "software", "full stack", "fullstack",
    "backend", "back-end", "frontend", "front-end", "python", "java",
    "node", "react", "devops", "sde",
]


class RemoteOKSource(Source):
    name = "remoteok"

    def search(self, queries=None, locations=None, remote=True):
        try:
            data = get_json("https://remoteok.com/api")
        except Exception as error:  # noqa: BLE001
            self.log(f"ERROR: {error}")
            return []

        jobs = []
        seen = set()

        for job in data:
            # The first element is a legal/metadata notice, not a job.
            if not isinstance(job, dict) or "position" not in job:
                continue

            title = job.get("position") or job.get("title") or ""
            tags = " ".join(job.get("tags") or [])
            haystack = f"{title} {tags}"

            if not (mentions_any(haystack, ENTRY) and mentions_any(haystack, DEV)):
                continue

            url = job.get("url") or job.get("apply_url")
            if url and url in seen:
                continue
            if url:
                seen.add(url)

            salary = ""
            if job.get("salary_min"):
                salary = f"{job.get('salary_min')} - {job.get('salary_max')}"

            desc = strip_html(job.get("description"))

            jobs.append(self.normalize(
                title=title,
                company=job.get("company"),
                url=url,
                location=job.get("location") or "Remote",
                salary=salary,
                snippet=desc[:400],
                description=desc,
                posted=job.get("date"),
                remote=True,
                origin="remoteok",
                query="remote entry-level dev",
            ))

        return jobs
