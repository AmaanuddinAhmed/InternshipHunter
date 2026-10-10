"""
Watchlist adapter — new openings straight from company careers pages.

Most startups host their careers page on Greenhouse, Lever or Ashby, and
all three publish a keyless JSON feed per company. `watchlist.json` (in the
project root) lists the companies to watch:

    [{"company": "Razorpay", "ats": "greenhouse",
      "slug": "razorpaysoftwareprivatelimited"}, ...]

Manage it with `python watchlist.py` (add / probe / check) or from the
Morning brief page. Jobs found here flow through the normal pipeline
(pre-filter -> AI score -> kit) with source = "watchlist".
"""

import html as _html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .base import Source, get_json, strip_html


WATCHLIST_FILE = Path(__file__).resolve().parent.parent / "watchlist.json"

ATS_NAMES = ("greenhouse", "lever", "ashby")

# A watched company can be global; only keep roles a Bengaluru-based
# candidate could take. Set "all_locations": true on an entry to keep all.
INDIA_HINTS = (
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai",
    "delhi", "gurgaon", "gurugram", "noida", "chennai", "kolkata",
    "ahmedabad", "remote", "anywhere", "apac",
)

CAREERS_URL_PATTERNS = [
    ("greenhouse", re.compile(r"greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)")),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)")),
]


# ----------------------------------------------------------------------
# watchlist.json
# ----------------------------------------------------------------------

def load_watchlist(path=WATCHLIST_FILE):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("slug")]


def save_watchlist(entries, path=WATCHLIST_FILE):
    entries = sorted(entries, key=lambda e: str(e.get("company", "")).lower())
    Path(path).write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def add_entry(company, ats, slug, path=WATCHLIST_FILE):
    """Add a company (no-op if that board is already listed). Returns the entry."""
    entries = load_watchlist(path)
    for entry in entries:
        if entry.get("ats") == ats and entry.get("slug", "").lower() == slug.lower():
            return entry
    entry = {"company": company, "ats": ats, "slug": slug}
    entries.append(entry)
    save_watchlist(entries, path)
    return entry


# ----------------------------------------------------------------------
# The three feeds. Each returns a list of plain dicts:
#   title, url, location, description, posted, job_type, remote
# and raises on HTTP errors (a 404 means "no such board").
# ----------------------------------------------------------------------

def _iso_from_ms(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def fetch_greenhouse(slug):
    data = get_json(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
        params={"content": "true"}, retries=0,
    )
    jobs = []
    for job in data.get("jobs") or []:
        location = (job.get("location") or {}).get("name") or ""
        jobs.append({
            "title": job.get("title") or "",
            "url": job.get("absolute_url") or "",
            "location": location,
            # `content` is HTML that has itself been HTML-escaped.
            "description": strip_html(_html.unescape(job.get("content") or "")),
            "posted": job.get("first_published") or job.get("updated_at") or "",
            "job_type": "",
            "remote": "remote" in location.lower(),
        })
    return jobs


def fetch_lever(slug):
    data = get_json(
        f"https://api.lever.co/v0/postings/{slug}",
        params={"mode": "json"}, retries=0,
    )
    jobs = []
    for job in data if isinstance(data, list) else []:
        categories = job.get("categories") or {}
        locations = categories.get("allLocations") or [categories.get("location") or ""]
        location = ", ".join(str(loc) for loc in locations if loc)
        if job.get("country") == "IN" and "india" not in location.lower():
            location = f"{location}, India".strip(", ")

        # The body is often split across `lists`, with descriptionPlain empty.
        parts = [job.get("descriptionPlain") or ""]
        for block in job.get("lists") or []:
            parts += [block.get("text") or "", strip_html(block.get("content") or "")]
        parts.append(job.get("additionalPlain") or "")

        jobs.append({
            "title": job.get("text") or "",
            "url": job.get("hostedUrl") or "",
            "location": location,
            "description": " ".join(p.strip() for p in parts if p and p.strip()),
            "posted": _iso_from_ms(job.get("createdAt")),
            "job_type": categories.get("commitment") or "",
            "remote": job.get("workplaceType") == "remote",
        })
    return jobs


def fetch_ashby(slug):
    data = get_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
        params={"includeCompensation": "true"}, retries=0,
    )
    jobs = []
    for job in data.get("jobs") or []:
        if job.get("isListed") is False:
            continue
        jobs.append({
            "title": job.get("title") or "",
            "url": job.get("jobUrl") or job.get("applyUrl") or "",
            "location": job.get("location") or "",
            "description": job.get("descriptionPlain")
                           or strip_html(job.get("descriptionHtml") or ""),
            "posted": job.get("publishedAt") or "",
            "job_type": job.get("employmentType") or "",
            "remote": bool(job.get("isRemote")),
        })
    return jobs


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


def fetch_board(ats, slug):
    return FETCHERS[ats](slug)


# ----------------------------------------------------------------------
# Finding a company's board
# ----------------------------------------------------------------------

def detect_from_url(url):
    """('lever', 'cred') from https://jobs.lever.co/cred/..., else None."""
    for ats, pattern in CAREERS_URL_PATTERNS:
        match = pattern.search(url or "")
        if match:
            return ats, match.group(1)
    return None


def slug_candidates(name, website=""):
    """Likely board slugs for a company name, most likely first."""
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    words = [w for w in words if w not in ("inc", "ltd", "llp", "pvt", "private", "limited")]
    candidates = ["".join(words), "-".join(words)]
    if words:
        candidates.append(words[0])
    host = re.sub(r"^https?://(www\.)?", "", (website or "").lower()).split("/")[0]
    if host:
        candidates.append(host.split(".")[0])
    seen, out = set(), []
    for candidate in candidates:
        if len(candidate) >= 2 and candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def probe(name, website=""):
    """
    Try the likely slugs against all three feeds. Returns
    (ats, slug, open_job_count) for the first board that exists, else None.
    A guessed slug can belong to a different company with a similar name —
    callers should show the result so it can be eyeballed.
    """
    for slug in slug_candidates(name, website):
        for ats in ATS_NAMES:
            try:
                jobs = fetch_board(ats, slug)
            except Exception:  # noqa: BLE001 - 404 = no such board
                continue
            return ats, slug, len(jobs)
    return None


# ----------------------------------------------------------------------
# The Source
# ----------------------------------------------------------------------

def _in_reach(job):
    location = (job.get("location") or "").lower()
    return job.get("remote") or not location or any(h in location for h in INDIA_HINTS)


class WatchlistSource(Source):
    name = "watchlist"

    def is_configured(self):
        return bool(load_watchlist())

    def search(self, queries=None, locations=None, remote=True):
        out = []

        for entry in load_watchlist():
            ats, slug = entry.get("ats"), entry.get("slug")
            company = entry.get("company") or slug

            if entry.get("enabled") is False or ats not in FETCHERS:
                continue

            try:
                jobs = fetch_board(ats, slug)
            except Exception as error:  # noqa: BLE001
                self.log(f"WARNING: {company} ({ats}/{slug}) unavailable: {error}")
                continue

            kept = 0
            for job in jobs:
                if not job["title"] or not job["url"]:
                    continue
                if not entry.get("all_locations") and not _in_reach(job):
                    continue
                out.append(self.normalize(
                    title=job["title"],
                    company=company,
                    url=job["url"],
                    location=job["location"] or "See job posting",
                    job_type=job["job_type"],
                    snippet=job["description"][:400],
                    description=job["description"],
                    posted=job["posted"],
                    remote=job["remote"],
                    origin=f"{ats}:{slug}",
                    query="watchlist",
                ))
                kept += 1

            self.log(f"{company}: {kept} in reach (of {len(jobs)} open)")

        return out
