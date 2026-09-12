"""
Wellfound adapter — public "role" job listings.

wellfound.com/jobs (the plain landing page) and wellfound.com/role/<role>
are server-rendered, plain-HTTP, unauthenticated pages that list real
openings with title, employment type, comp, experience level, and
location. Only the *deep-filter* URLs (wellfound.com/role/l/<role>/<city>)
sit behind DataDome/Cloudflare bot protection — this adapter deliberately
avoids those and only reads the plain, unprotected role pages.

Best-effort adapter:
- Reads public job pages only, no login, no applications submitted.
- If Wellfound changes markup, adds protection to these pages, or blocks
  the request, this logs a warning and returns [] — it must never break
  the rest of the discovery run.
"""

import re

from .base import Source, get_text, strip_html


# Plain (non deep-filter) role pages, paginated with ?page=N.
ROLE_SLUGS = ["software-engineer"]
MAX_PAGES_PER_ROLE = 3
MAX_JOBS = 40

ENTRY_TERMS = (
    "intern",
    "internship",
    "junior",
    "new grad",
    "entry level",
    "entry-level",
    "graduate",
    "0 years of exp",
    "1 year of exp",
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

# Experience phrases like "3 years of exp", "5+ years of exp" — used both
# as a senior signal (>=2 years) and to confirm entry-level (0-1 years).
EXPERIENCE_PATTERN = re.compile(
    r"(\d+)\s*\+?\s*years?\s+of\s+exp", re.IGNORECASE
)

# One job row:
#   <a href="/jobs/<id>-<slug>">Title</a>Full-time
#   ...comp/equity...
#   ...location...
#   ...years of exp (optional)...
#   ...posted...
# up to the next job link or the next company-profile link.
JOB_LINK_PATTERN = re.compile(
    r'<a[^>]+href=["\'](?P<url>/jobs/[^"\']+)["\'][^>]*>'
    r'(?P<title>.*?)</a>'
    r'(?P<meta>.*?)'
    r'(?=<a[^>]+href=["\']/jobs/|<a[^>]+href=["\']/company/|\Z)',
    re.IGNORECASE | re.DOTALL,
)

# The nearest preceding company-profile heading link, used to attribute
# a company name to the job rows that follow it. Matches an <a> to
# /company/<slug> whose visible text is the company name (not a bare
# <img> wrapper, which has no text).
COMPANY_HEADER_PATTERN = re.compile(
    r'<a[^>]+href=["\']/company/[^"\']+["\'][^>]*>'
    r'(?P<company>(?:(?!</a>).)*?[A-Za-z].*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def _clean_meta(meta_html):
    # Mark block-level boundaries with a pipe before stripping tags, so
    # sibling <div> fields (comp, location, experience, posted) don't run
    # together with no separator once the HTML tags are gone.
    marked = re.sub(
        r"</(?:div|span|li|p)>", "|", meta_html, flags=re.IGNORECASE
    )
    text = strip_html(marked)
    # Collapse "Save Apply" / stray UI text that trails each row.
    text = re.sub(r"\bSave\b\s*\bApply\b", "", text, flags=re.IGNORECASE)
    # Normalize the boundary markers into a consistent separator.
    text = re.sub(r"\s*\|\s*", " | ", text)
    return re.sub(r"\s+", " ", text).strip(" |")


class WellfoundSource(Source):
    name = "wellfound"

    def search(self, queries=None, locations=None, remote=True):
        all_jobs = []
        seen = set()

        for slug in ROLE_SLUGS:
            for page in range(1, MAX_PAGES_PER_ROLE + 1):
                page_url = f"https://wellfound.com/role/{slug}"
                if page > 1:
                    page_url += f"?page={page}"

                page_jobs = self._search_page(page_url, seen)
                all_jobs.extend(page_jobs)

                if len(all_jobs) >= MAX_JOBS:
                    break
            if len(all_jobs) >= MAX_JOBS:
                break

        all_jobs = all_jobs[:MAX_JOBS]

        if not all_jobs:
            self.log(
                "WARNING: no usable public job listings found "
                "on any Wellfound role page; skipping this source."
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

        # Build an ordered list of (position, company) from the company
        # headers, so each job row can look up the nearest one before it.
        company_markers = [
            (m.start(), strip_html(m.group("company")).strip())
            for m in COMPANY_HEADER_PATTERN.finditer(html)
        ]

        jobs = []

        for match in JOB_LINK_PATTERN.finditer(html):

            url = match.group("url")
            title = strip_html(match.group("title")).strip()
            meta_html = match.group("meta") or ""

            if not title or not url:
                continue

            full_url = "https://wellfound.com" + url

            if full_url in seen:
                continue
            seen.add(full_url)

            # Company = the last header that appears before this job link.
            job_pos = match.start()
            company = ""
            for pos, name in company_markers:
                if pos <= job_pos:
                    company = name
                else:
                    break

            meta_text = _clean_meta(meta_html)
            haystack = f"{title} {meta_text}".lower()

            exp_match = EXPERIENCE_PATTERN.search(meta_text)
            exp_years = int(exp_match.group(1)) if exp_match else None

            is_senior = any(term in haystack for term in SENIOR_TERMS)
            if exp_years is not None and exp_years >= 3:
                is_senior = True
            if is_senior:
                continue

            is_entry_signal = any(term in haystack for term in ENTRY_TERMS)
            if exp_years is not None and exp_years <= 1:
                is_entry_signal = True
            if not is_entry_signal:
                continue

            is_remote = "remote" in meta_text.lower()

            # Comp (e.g. "$130k – $210k • 0.05% – 0.2%") is the field
            # segment (split on the "|" div-boundary marker inserted by
            # _clean_meta) that contains a currency symbol or "equity".
            salary = ""
            for segment in meta_text.split("|"):
                segment = segment.strip(" •")
                if re.search(r"[$₹€£]|equity", segment, re.IGNORECASE):
                    segment = re.sub(
                        r"^(Full-time|Part-time|Contract|Internship)\s*",
                        "",
                        segment,
                        flags=re.IGNORECASE,
                    ).strip()
                    salary = segment
                    break

            display_meta = re.sub(r"\s*\|\s*", " • ", meta_text).strip(" •")

            jobs.append(
                self.normalize(
                    title=title,
                    company=company or "Startup on Wellfound",
                    url=full_url,
                    location="See job posting",
                    salary=salary,
                    job_type="Internship" if "intern" in haystack else "Full-time",
                    snippet=display_meta[:300],
                    description=display_meta,
                    posted="",
                    remote=is_remote,
                    origin="wellfound",
                    query="wellfound software engineer entry-level",
                )
            )

            if len(jobs) >= MAX_JOBS:
                break

        self.log(f"{page_url}: found {len(jobs)}")

        return jobs