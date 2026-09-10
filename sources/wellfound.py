"""
Wellfound adapter — public startup job listings.

Best-effort adapter:
- Reads public job pages only.
- Does not log in.
- Does not submit applications.
- Fails gracefully if the site blocks requests or changes markup.
"""

import re

from .base import Source, get_text, strip_html


BASE_URL = "https://wellfound.com/jobs"


class WellfoundSource(Source):
    name = "wellfound"

    def search(self, queries=None, locations=None, remote=True):
        jobs = []

        try:
            html = get_text(
                BASE_URL,
                timeout=20,
            )
        except Exception as error:  # noqa: BLE001
            self.log(f"WARNING: {error}")
            return []

        if not html:
            self.log("WARNING: empty response")
            return []

        # Wellfound is dynamically rendered and its markup can change.
        # Try to extract public job links if they are present.
        pattern = re.compile(
            r'href=["\']([^"\']*?/jobs/[^"\']+)["\']'
            r'[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )

        seen = set()

        excluded_terms = (
            "sales",
            "business development",
            "marketing",
            "human resources",
            "recruitment",
            "recruiter",
            "customer success",
            "customer support",
            "account executive",
            "operations",
            "finance",
            "legal",
        )

        technical_terms = (
            "software",
            "software engineer",
            "software developer",
            "developer",
            "engineering",
            "full stack",
            "fullstack",
            "frontend",
            "front end",
            "backend",
            "back end",
            "web developer",
            "python",
            "java",
            "javascript",
            "typescript",
            "react",
            "node",
            "angular",
            "django",
            "php",
            "flutter",
            "android",
            "ios",
            "machine learning",
            "artificial intelligence",
            "ai/ml",
            "data science",
            "devops",
            "cloud",
            "cyber security",
            "qa",
            "testing",
        )

        for match in pattern.finditer(html):

            url = match.group(1)
            title_html = match.group(2)

            title = strip_html(title_html).strip()

            if not title:
                continue

            if url.startswith("/"):
                url = "https://wellfound.com" + url

            if url in seen:
                continue

            seen.add(url)

            haystack = title.lower()

            if any(
                term in haystack
                for term in excluded_terms
            ):
                continue

            if not any(
                term in haystack
                for term in technical_terms
            ):
                continue

            jobs.append(
                self.normalize(
                    title=title,
                    company="",
                    url=url,
                    location="Global / Remote",
                    job_type="Internship",
                    snippet=title,
                    description=title,
                    posted="",
                    remote=True,
                    origin="wellfound",
                    query="software engineering internship",
                )
            )

            if len(jobs) >= 25:
                break

        if not jobs:
            self.log(
                "WARNING: no usable public job listings found; "
                "skipping this source."
            )

        return jobs
