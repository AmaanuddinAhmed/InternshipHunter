"""
Jobicy adapter — free remote jobs API (keyless).
https://jobicy.com/api/v2/remote-jobs
"""

from .base import Source, get_json, strip_html, mentions_any


ENTRY = ["intern", "internship", "junior", "graduate", "trainee", "entry"]


class JobicySource(Source):
    name = "jobicy"

    def search(self, queries=None, locations=None, remote=True):
        jobs = []
        seen = set()

        # Jobicy supports industry tags; dev/engineering are the relevant ones.
        for industry in ["dev", "engineering"]:
            try:
                data = get_json(
                    "https://jobicy.com/api/v2/remote-jobs",
                    params={"count": 50, "industry": industry},
                )
            except Exception as error:  # noqa: BLE001
                self.log(f"ERROR {industry!r}: {error}")
                continue

            for job in data.get("jobs", []):
                title = job.get("jobTitle") or ""
                level = job.get("jobLevel") or ""

                # Keep only entry-level-ish roles.
                if not mentions_any(f"{title} {level}", ENTRY):
                    continue

                url = job.get("url")
                if url and url in seen:
                    continue
                if url:
                    seen.add(url)

                salary = ""
                if job.get("salaryMin"):
                    salary = (
                        f"{job.get('salaryMin')} - "
                        f"{job.get('salaryMax')} "
                        f"{job.get('salaryCurrency', '')} "
                        f"{job.get('salaryPeriod', '')}"
                    ).strip()

                desc = strip_html(job.get("jobDescription"))
                snippet = strip_html(job.get("jobExcerpt")) or desc[:400]

                jobs.append(self.normalize(
                    title=title,
                    company=job.get("companyName"),
                    url=url,
                    location=job.get("jobGeo"),
                    salary=salary,
                    job_type=", ".join(job.get("jobType") or []),
                    snippet=snippet,
                    description=desc,
                    posted=job.get("pubDate"),
                    remote=True,
                    origin="jobicy",
                    query=f"{industry} entry-level",
                ))

        return jobs
