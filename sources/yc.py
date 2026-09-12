"""
YC adapter — public "Work at a Startup" job listings.

ycombinator.com/jobs/role/... is server-rendered plain HTML (no login,
no JS execution needed) and lists real openings with company, batch,
title, employment type, department, comp and location. We fetch a
handful of role/location-filtered pages relevant to this candidate and
parse the listing cards with regex, matching the style of the other
best-effort adapters in this package (internshala.py, wellfound.py).

Best-effort adapter:
- Reads public job pages only, no login, no applications submitted.
- If YC changes markup or blocks the request, logs a warning and
  returns [] — it must never break the rest of the discovery run.
"""

import re

from .base import Source, get_text, strip_html


# Role + location combinations that matter for this candidate. Each is a
# real YC route (confirmed against ycombinator.com/jobs/role/... pages).
PAGES = [
    "https://www.ycombinator.com/jobs/role/software-engineer/india",
    "https://www.ycombinator.com/jobs/role/software-engineer/remote",
]

MAX_PER_PAGE = 40

ENTRY_TERMS = (
    "intern",
    "internship",
    "junior",
    "new grad",
    "entry level",
    "entry-level",
    "graduate",
)

SENIOR_TERMS = (
    "senior",
    "staff",
    "principal",
    "lead",
    "manager",
    "director",
    "founding",
)

# A job-title link, e.g.:
#   <a href="/companies/frontpage/jobs/i7yAbdy-software-engineering-intern-...">
#     Software Engineering Intern: AI-Native Product Engineering
#   </a>
# followed by the metadata line:
#   Full-time • Engineering • Full stack • $130K - $170K • Bengaluru, KA, IN
JOB_LINK_PATTERN = re.compile(
    r'<a[^>]+href=["\'](?P<url>/companies/(?P<slug>[^"\'/]+)/jobs/[^"\']+)'
    r'["\'][^>]*>(?P<title>.*?)</a>'
    r'(?P<meta>.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)

# A company-profile link with actual visible text (name + batch), used to
# recover the company name for the block immediately preceding a job link.
# The listing markup may also wrap the same href around a bare <img>, which
# has no text — we only want the text-bearing occurrence.
COMPANY_LINK_PATTERN = re.compile(
    r'<a[^>]+href=["\']/companies/(?P<slug>[^"\']+)["\'][^>]*>'
    r'(?P<label>(?:(?!</a>).)*?[A-Za-z].*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def _split_meta(meta_text):
    """
    The meta line looks like:
        Full-time • Engineering • Full stack • $130K - $170K • Bengaluru, KA, IN
    or without comp:
        Internship • Engineering • Full stack • Bengaluru, KA, IN
    Split on the bullet separator and return the cleaned parts.
    """
    parts = [
        p.strip()
        for p in re.split(r"\u2022|\|", meta_text)
        if p.strip()
    ]
    return parts


class YCSource(Source):
    name = "yc"

    def search(self, queries=None, locations=None, remote=True):
        all_jobs = []
        seen = set()

        for page_url in PAGES:
            page_jobs = self._search_page(page_url, seen)
            all_jobs.extend(page_jobs)

        if not all_jobs:
            self.log(
                "WARNING: no usable public job listings found "
                "on any YC page; skipping this source."
            )

        return all_jobs

    def _search_page(self, page_url, seen):
        try:
            html = get_text(page_url, timeout=20)
        except Exception as error:  # noqa: BLE001
            self.log(f"WARNING: {page_url} unavailable: {error}")
            return []

        if not html:
            self.log(f"WARNING: empty response from {page_url}")
            return []

        # Index every company-slug -> visible name we can find on the page,
        # so each job card can look its company up rather than relying on
        # markup position (which varies with wrapper <img> anchors).
        company_by_slug = {}
        for cmatch in COMPANY_LINK_PATTERN.finditer(html):
            slug = cmatch.group("slug")
            label = strip_html(cmatch.group("label")).strip()
            if slug and label and slug not in company_by_slug:
                company_by_slug[slug] = label

        jobs = []

        for match in JOB_LINK_PATTERN.finditer(html):

            url = match.group("url")
            slug = match.group("slug")
            title = strip_html(match.group("title")).strip()
            meta_html = match.group("meta") or ""

            if not title or not url:
                continue

            full_url = "https://www.ycombinator.com" + url

            if full_url in seen:
                continue
            seen.add(full_url)

            # Strip trailing "(W22)" / "(S21)" batch tags from the name.
            company = company_by_slug.get(slug, "")
            company = re.sub(r"\s*\([A-Z]\d{2}\)\s*", " ", company).strip()

            meta_text = strip_html(meta_html)
            parts = _split_meta(meta_text)

            job_type = parts[0] if len(parts) > 0 else ""
            location = parts[-1] if len(parts) > 1 else ""

            haystack = f"{title} {job_type}".lower()

            is_senior = any(term in haystack for term in SENIOR_TERMS)
            if is_senior:
                continue

            is_entry_signal = (
                any(term in haystack for term in ENTRY_TERMS)
                or "intern" in job_type.lower()
            )
            if not is_entry_signal:
                continue

            is_remote = "remote" in location.lower()

            jobs.append(
                self.normalize(
                    title=title,
                    company=company or "YC Startup",
                    url=full_url,
                    location=location or "See job posting",
                    job_type=job_type,
                    snippet=meta_text[:300],
                    description=meta_text,
                    posted="",
                    remote=is_remote,
                    origin="yc",
                    query="YC internship india/remote",
                )
            )

            if len(jobs) >= MAX_PER_PAGE:
                break

        self.log(f"{page_url.rsplit('/', 2)[-1]}: found {len(jobs)}")

        return jobs