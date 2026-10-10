"""
Unstop adapter — public internship listings.

The listing page itself is rendered in the browser, so its HTML holds no
jobs. The page loads them from a public JSON endpoint, which is what this
adapter reads (no key, no login):

    https://unstop.com/api/public/opportunity/search-result
        ?opportunity=internships&oppstatus=open&searchTerm=...&per_page=...

Best-effort: any failure logs a warning and returns [].
"""

from .base import Source, get_json, strip_html


API = "https://unstop.com/api/public/opportunity/search-result"

SEARCH_TERMS = ["software", "developer", "full stack", "backend", "web"]
PER_PAGE = 30

# Unstop's search is loose ("software" also returns "Software Sales
# Internship"), so obvious non-engineering titles are dropped here rather
# than spending an AI call on them.
NON_TECH_TITLE_TERMS = (
    "sales", "marketing", "business development", "human resource",
    " hr ", "recruit", "content", "social media", "customer", "telecall",
    "operations", "finance", "account", "graphic", "video", "legal",
    "campus ambassador",
)


def _stipend(detail):
    if not detail or detail.get("not_disclosed") or not detail.get("show_salary"):
        return ""
    if detail.get("paid_unpaid") == "unpaid":
        return "Unpaid"
    low, high = detail.get("min_salary"), detail.get("max_salary")
    if not low and not high:
        return ""
    amount = f"₹{low:,} – ₹{high:,}" if low and high and low != high else f"₹{(high or low):,}"
    period = {"monthly": "/month", "yearly": "/year"}.get(detail.get("pay_in"), "")
    return amount + period


class UnstopSource(Source):
    name = "unstop"

    def search(self, queries=None, locations=None, remote=True):
        jobs = []
        seen = set()

        for term in SEARCH_TERMS:
            try:
                payload = get_json(API, params={
                    "opportunity": "internships",
                    "oppstatus": "open",
                    "searchTerm": term,
                    "per_page": PER_PAGE,
                    "page": 1,
                })
            except Exception as error:  # noqa: BLE001
                self.log(f"WARNING: '{term}' search failed: {error}")
                continue

            items = ((payload or {}).get("data") or {}).get("data") or []

            for item in items:
                url = item.get("seo_url") or ""
                title = item.get("title") or ""

                if not url or not title or url in seen:
                    continue
                seen.add(url)

                if any(t in f" {title.lower()} " for t in NON_TECH_TITLE_TERMS):
                    continue

                detail = item.get("jobDetail") or {}
                cities = [
                    loc.get("city") for loc in (item.get("locations") or [])
                    if loc.get("city")
                ] or list(detail.get("locations") or [])
                is_remote = (
                    item.get("region") == "online"
                    and detail.get("type") not in ("in_office", "hybrid")
                )
                location = ", ".join(cities) or ("Remote" if is_remote else "India")

                skills = ", ".join(
                    s.get("skill") or "" for s in (item.get("required_skills") or [])
                )
                description = strip_html(item.get("details") or "")
                if skills:
                    description += f" Skills: {skills}."

                jobs.append(self.normalize(
                    title=title,
                    company=(item.get("organisation") or {}).get("name") or "",
                    url=url,
                    location=location,
                    salary=_stipend(detail),
                    job_type="Internship",
                    snippet=description[:400],
                    description=description,
                    posted=item.get("updated_at") or "",
                    remote=is_remote,
                    origin="unstop.com",
                    query=term,
                ))

        return jobs
