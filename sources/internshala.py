"""
Internshala adapter — public internship listings.

Reads the software / web development category pages (Bangalore and
work-from-home) instead of the all-categories front page, and pulls the
company, location and stipend out of each listing card.

Best-effort: no login, nothing submitted; if a page is blocked or the
markup changes, it logs a warning and returns what it could read.
"""

import re

from .base import Source, get_text, strip_html


PAGES = [
    "https://internshala.com/internships/software-development-internship-in-bangalore/",
    "https://internshala.com/internships/web-development-internship-in-bangalore/",
    "https://internshala.com/internships/work-from-home-software-development-internships/",
    "https://internshala.com/internships/work-from-home-web-development-internships/",
]

MAX_JOBS = 60

DETAIL_LINK = re.compile(
    r'<a[^>]+href=["\'](?P<url>[^"\']*/internship/detail/[^"\']+)["\'][^>]*>'
    r'(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def _by_class(card, class_fragment):
    """Text of the first element whose class attribute contains the fragment."""
    match = re.search(
        r'<(\w+)[^>]*class=["\'][^"\']*' + re.escape(class_fragment)
        + r'[^"\']*["\'][^>]*>(.*?)</\1>',
        card, re.IGNORECASE | re.DOTALL,
    )
    return strip_html(match.group(2)) if match else ""


def _company_from_url(url):
    """.../detail/<role>-internship-at-acme-labs1790309126  ->  'Acme Labs'"""
    match = re.search(r"-at-([a-z0-9-]+?)\d{6,}/?$", url.lower())
    if not match:
        return ""
    return match.group(1).replace("-", " ").strip().title()


class InternshalaSource(Source):
    name = "internshala"

    def search(self, queries=None, locations=None, remote=True):
        jobs = []
        seen = set()

        for page_url in PAGES:
            try:
                html = get_text(
                    page_url, timeout=20, headers={"Accept": "text/html"}
                )
            except Exception as error:  # noqa: BLE001
                self.log(f"WARNING: {page_url} unavailable: {error}")
                continue

            from_home = "work-from-home" in page_url
            links = list(DETAIL_LINK.finditer(html or ""))
            found = 0

            for index, match in enumerate(links):
                url = match.group("url")
                title = strip_html(match.group("title"))

                if url.startswith("/"):
                    url = "https://internshala.com" + url

                # The same card links to the detail page more than once
                # (title, "View details"); only the titled one is a job.
                if not title or url in seen or title.lower() == "view details":
                    continue
                seen.add(url)

                # Everything up to the next listing's link belongs to this card.
                end = links[index + 1].start() if index + 1 < len(links) else len(html)
                card = html[match.end():min(end, match.end() + 6000)]

                company = _by_class(card, "company-name") or _company_from_url(url)
                location = _by_class(card, "locations") or (
                    "Work from home" if from_home else "Bangalore"
                )
                stipend = _by_class(card, "stipend")

                jobs.append(self.normalize(
                    title=title,
                    company=company,
                    url=url,
                    location=location,
                    salary=stipend,
                    job_type="Internship",
                    snippet=f"{title} internship at {company}".strip(),
                    description=f"{title} internship at {company}. "
                                f"Location: {location}. Stipend: {stipend or 'not shown'}.",
                    remote=from_home,
                    origin="internshala.com",
                    query=page_url.rstrip("/").rsplit("/", 1)[-1],
                ))
                found += 1

                if len(jobs) >= MAX_JOBS:
                    break

            self.log(f"{page_url.rstrip('/').rsplit('/', 1)[-1]}: {found}")

            if len(jobs) >= MAX_JOBS:
                break

        return jobs
