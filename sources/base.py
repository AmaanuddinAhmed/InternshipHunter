"""
Shared foundation for all job-source adapters.

Every source (API or scraper) subclasses `Source` and returns jobs in one
normalized shape via `self.normalize(...)`, so everything downstream
(pipeline.py, batch_analyzer.py, crm_importer.py) can stay source-agnostic.
"""

import hashlib
import html as _html
import re
import time
from datetime import datetime

import requests


DEFAULT_TIMEOUT = 30

# A polite, honest UA. We only read public listings, at low volume.
USER_AGENT = (
    "Mozilla/5.0 (compatible; InternshipHunter/1.0; personal job search)"
)


def clean_text(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def strip_html(value):
    """Turn an HTML job description into readable plain text."""
    if not value:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", str(value),
                  flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def mentions_any(text, terms):
    """True if any term appears in text (case-insensitive)."""
    low = (text or "").lower()
    return any(term in low for term in terms)


def make_job_id(source, url, title=""):
    """
    Stable id derived from the most reliable identifier available.
    URL remains the primary identity key downstream; this is mainly
    for a readable, deterministic per-source id.
    """
    basis = (url or title or "").strip().lower()
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
    return f"{source}-{digest}"


def _request(method, url, *, params=None, json=None, headers=None,
             timeout=DEFAULT_TIMEOUT, retries=2):
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        merged.update(headers)

    last_error = None

    for attempt in range(retries + 1):
        try:
            resp = requests.request(
                method,
                url,
                params=params,
                json=json,
                headers=merged,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp
        except Exception as error:  # noqa: BLE001 - surfaced to caller
            last_error = error
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))

    raise last_error


def get_json(url, *, params=None, headers=None, timeout=DEFAULT_TIMEOUT,
             retries=2):
    return _request(
        "GET", url,
        params=params, headers=headers, timeout=timeout, retries=retries,
    ).json()

def get_text(url, *, params=None, headers=None, timeout=DEFAULT_TIMEOUT,
             retries=2):
    """Fetch a public HTML/text page and return its response body."""
    return _request(
        "GET", url,
        params=params,
        headers=headers,
        timeout=timeout,
        retries=retries,
    ).text

def post_json(url, *, json=None, headers=None, timeout=DEFAULT_TIMEOUT,
              retries=2):
    return _request(
        "POST", url,
        json=json, headers=headers, timeout=timeout, retries=retries,
    ).json()


class Source:
    """Base class for a job source. Subclasses set `name` and implement `search`."""

    name = "base"
    enabled = True

    def is_configured(self):
        """
        Override for sources that need an API key. Returning False makes the
        registry skip this source instead of crashing the whole run.
        """
        return True

    def search(self, queries, locations, remote=True):
        """Return a list of normalized job dicts. Must be implemented."""
        raise NotImplementedError

    def log(self, message):
        print(f"  [{self.name}] {message}")

    def normalize(self, *, title, company, url, location="", salary="",
                  job_type="", snippet="", description="", posted="",
                  remote=False, origin="", query=""):
        """
        Produce the canonical job shape. Keeps the keys the existing pipeline
        already relies on (title, company, location, salary, type, source,
        url, updated, snippet) and adds remote / description / posted / origin.
        """
        title = clean_text(title)
        url = clean_text(url)
        snippet = clean_text(snippet)
        description = clean_text(description) or snippet

        return {
            "job_id": make_job_id(self.name, url, title),
            "title": title,
            "company": clean_text(company),
            "location": clean_text(location),
            "remote": bool(remote),
            "salary": clean_text(salary),
            "type": clean_text(job_type),
            "source": self.name,
            "origin": clean_text(origin),
            "url": url,
            "updated": clean_text(posted),
            "posted": clean_text(posted),
            "snippet": snippet,
            "description": description,
            "search_query": clean_text(query),
            "found_at": datetime.now().isoformat(),
        }
