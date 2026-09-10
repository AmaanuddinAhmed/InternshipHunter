"""
Internshala adapter — public internship listings.

Best-effort adapter:
- Uses public listing pages.
- Does not log in.
- Does not submit applications.
- Fails gracefully if the site blocks requests or changes markup.
"""

import re

from .base import Source, get_text, strip_html

BASE_URL = "https://internshala.com/internships/"


class InternshalaSource(Source):
    name = "internshala"

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
            return []

        # Internshala markup can change frequently.
        # Keep extraction deliberately conservative.
        pattern = re.compile(
            r'href=["\']([^"\']*/internship/detail/[^"\']+)["\']'
            r'[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )

        seen = set()

        for match in pattern.finditer(html):

            url = match.group(1)
            title_html = match.group(2)

            title = strip_html(title_html).strip()

            if not title or url in seen:
                continue

            seen.add(url)

            if url.startswith("/"):
                url = "https://internshala.com" + url

            haystack = title.lower() 

            # ------------------------------------------------
            # HARD EXCLUSIONS
            # ------------------------------------------------

            excluded_terms = (
                "sales",
                "business development",
                "business development (sales)",
                "marketing",
                "human resources",
                "hr",
                "recruitment",
                "recruiter",
                "content writing",
                "content writer",
                "social media",
                "customer support",
                "customer service",
                "telecalling",
                "telecaller",
                "operations",
                "finance",
                "accounts",
                "graphic design",
                "video editing",
                "law",
                "legal",
                "management",
            )

            if any(term in haystack for term in excluded_terms):
                continue

            technical_terms = (
                "software",
                "software engineer",
                "software engineering",
                "software developer",
                "developer",
                "software development",
                "web development",
                "application development",
                "mobile development",
                "full stack",
                "fullstack",
                "frontend",
                "front end",
                "backend",
                "back end",
                "web developer",
                "flutter",
                "android",
                "ios",
                "python",
                "java",
                "javascript",
                "react",
                "node",
                "django",
                "php",
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

            # 1. Reject obvious non-tech roles
            if any(term in haystack for term in excluded_terms):
                continue

            # 2. Require a genuine technical role
            if not any(term in haystack for term in technical_terms):
                continue

            jobs.append(
                self.normalize(
                    title=title,
                    company="",
                    url=url,
                    location="India",
                    job_type="Internship",
                    snippet=title,
                    description=title,
                    posted="",
                    remote=False,
                    origin="internshala",
                    query="software engineering internship",
                )
            )

            if len(jobs) >= 25:
                break

        return jobs
