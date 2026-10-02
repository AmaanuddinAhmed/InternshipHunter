"""
Full job-description fetcher.

Aggregator APIs only return a short snippet (Jooble ~300 characters,
Adzuna 500), which is thin evidence for scoring a job or writing a cover
letter. This module turns a job URL into the full posting text.

- With FIRECRAWL_API_KEY in .env, the page is fetched through Firecrawl's
  scrape API, which renders JavaScript and returns clean markdown.
- Without a key, a plain HTTP fetch is attempted. That only works for
  server-rendered pages, and is only used when you add a job by hand.

Best-effort: any failure returns "" and the caller carries on with
whatever text it already had. Nothing here logs in or submits anything.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"

# A description shorter than this is treated as "just a snippet".
THIN_JD_CHARS = 800

# Keep prompts bounded; a real JD rarely needs more than this.
MAX_JD_CHARS = 12000

_CACHE = {}


def is_configured():
    return bool(os.getenv("FIRECRAWL_API_KEY"))


def is_thin(job):
    return len(str(job.get("description") or "").strip()) < THIN_JD_CHARS


def _firecrawl_markdown(url):
    response = requests.post(
        FIRECRAWL_SCRAPE_URL,
        headers={
            "Authorization": f"Bearer {os.getenv('FIRECRAWL_API_KEY')}",
            "Content-Type": "application/json",
        },
        json={
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
        },
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or payload
    return str(data.get("markdown") or "").strip()


def _plain_text(url):
    from sources.base import get_text, strip_html

    return strip_html(get_text(url, timeout=20, retries=0))


def fetch_job_description(url, allow_plain_fallback=False):
    """Return the full posting text for `url`, or "" if it can't be read."""
    url = str(url or "").strip()

    if not url.lower().startswith(("http://", "https://")):
        return ""

    if url in _CACHE:
        return _CACHE[url]

    text = ""

    if is_configured():
        try:
            text = _firecrawl_markdown(url)
        except Exception as error:  # noqa: BLE001 - best effort
            print(f"    (Firecrawl could not read the posting: {error})")

    if not text and allow_plain_fallback:
        try:
            text = _plain_text(url)
        except Exception as error:  # noqa: BLE001 - best effort
            print(f"    (Plain fetch could not read the posting: {error})")

    text = text[:MAX_JD_CHARS]
    _CACHE[url] = text
    return text


def enrich_job(job, allow_plain_fallback=False):
    """
    Return the job with a full description when the current one is thin
    and a clearly longer one can be fetched. Otherwise return it unchanged.
    """
    if not is_thin(job):
        return job

    current = str(job.get("description") or "").strip()
    full = fetch_job_description(
        job.get("url"), allow_plain_fallback=allow_plain_fallback
    )

    if len(full) < len(current) + 200:
        return job

    return {**job, "description": full, "jd_source": "full_page"}