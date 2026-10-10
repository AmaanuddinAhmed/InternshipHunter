"""
Company leads — startups worth contacting before they post a role.

Two feeds, both free and keyless:

- YC companies that are based in India and marked as hiring, from the
  open yc-oss dataset (refreshed daily from the YC directory).
- Indian startups in this week's funding news (Google News RSS + Inc42).
  A company that just raised money usually hires within months.

    python leads.py          refresh leads.json and print what is new

Leads are companies, not job postings: the point is to message someone
there (see outreach.py), and to add the company to the watchlist
(`python watchlist.py probe --leads`).
"""

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

from sources.base import clean_text, get_json, get_text


BASE = Path(__file__).resolve().parent
LEADS_FILE = BASE / "leads.json"

YC_URLS = [
    "https://yc-oss.github.io/api/companies/hiring.json",
    "https://raw.githubusercontent.com/yc-oss/api/main/companies/hiring.json",
]
YC_MAX_TEAM_SIZE = 300          # past this size, cold outreach rarely works

NEWS_QUERIES = [
    "startup raises funding Bengaluru",
    "Indian startup raises seed round",
    "Indian startup raises Series A",
]
NEWS_FEEDS = [
    "https://news.google.com/rss/search?q={q}+when:7d&hl=en-IN&gl=IN&ceid=IN:en"
    .format(q=quote_plus(query))
    for query in NEWS_QUERIES
] + ["https://inc42.com/buzz/feed/"]

FUNDING_MAX_AGE_DAYS = 14

# "Acme raises $5M in Series A led by ..."  ->  company="Acme", rest="$5M in ..."
HEADLINE = re.compile(
    r"^(?P<company>.{2,60}?)\s+"
    r"(?:raises|raised|secures|secured|bags|bagged|closes|lands|nets|snags|"
    r"picks up|gets|mops up|pockets)\s+"
    r"(?P<rest>.+)$",
    re.IGNORECASE,
)
AMOUNT = re.compile(
    r"(?:\$|usd|rs\.?|inr|₹)\s?[\d.,]+\s?(?:mn|million|m|bn|billion|cr|crore|k|lakh)?\b"
    r"|[\d.,]+\s?(?:mn|million|cr|crore)\b",
    re.IGNORECASE,
)
ROUND = re.compile(
    r"\b(pre-seed|seed|pre-series [a-d]|series [a-h]|bridge|angel)\b", re.IGNORECASE
)
# Words that open a headline but are not part of the company name.
LEAD_INS = re.compile(
    r"^(?:exclusive|breaking|funding alert|funding)\s*[:|\-–]\s*"
    r"|^(?:\w[\w-]*\s){0,4}?(?:startup|firm|platform|company|unicorn|maker|brand)\s+",
    re.IGNORECASE,
)


def _now():
    return datetime.now(timezone.utc)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ----------------------------------------------------------------------
# leads.json
# ----------------------------------------------------------------------

def load_leads(path=LEADS_FILE):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [lead for lead in data if isinstance(lead, dict) and lead.get("id")]


def save_leads(leads, path=LEADS_FILE):
    Path(path).write_text(
        json.dumps(leads, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def set_status(lead_id, status, path=LEADS_FILE):
    """status: new | contacted | dismissed. Returns the lead, or None."""
    leads = load_leads(path)
    for lead in leads:
        if lead["id"] == lead_id:
            lead["status"] = status
            save_leads(leads, path)
            return lead
    return None


# ----------------------------------------------------------------------
# Feed 1: YC companies in India that are hiring
# ----------------------------------------------------------------------

def fetch_yc_leads():
    companies = None
    for url in YC_URLS:
        try:
            companies = get_json(url, retries=1)
            break
        except Exception as error:  # noqa: BLE001
            print(f"  [leads] YC list not reachable at {url.split('/')[2]}: {error}")
    if not isinstance(companies, list):
        return []

    leads = []
    for company in companies:
        locations = company.get("all_locations") or ""
        if "india" not in locations.lower():
            continue
        if company.get("status") not in (None, "Active"):
            continue
        team_size = company.get("team_size") or 0
        if team_size > YC_MAX_TEAM_SIZE:
            continue
        leads.append({
            "id": f"yc:{company.get('slug')}",
            "kind": "yc",
            "name": company.get("name") or "",
            "about": company.get("one_liner") or "",
            "website": company.get("website") or "",
            "url": company.get("url") or "",
            "location": locations,
            "team_size": team_size,
            "detail": f"YC {company.get('batch') or ''} · "
                      f"{team_size or '?'} people · hiring".strip(),
        })
    return leads


# ----------------------------------------------------------------------
# Feed 2: funding news
# ----------------------------------------------------------------------

def parse_funding_headline(title):
    """
    {'company', 'amount', 'round'} for a funding headline, else None.
    Deliberately strict: a headline that does not clearly name who raised
    money is skipped rather than guessed at.
    """
    # Google News appends " - Publisher"; drop it.
    title = clean_text(re.sub(r"\s+[-–|]\s+[^-–|]{2,40}$", "", title or ""))
    match = HEADLINE.match(title)
    if not match:
        return None

    company = LEAD_INS.sub("", match.group("company")).strip(" ,:'\"’‘")
    rest = match.group("rest")
    amount = AMOUNT.search(rest)

    if not company or not amount or len(company.split()) > 5:
        return None
    if not company[0].isalnum() or company.lower() in ("startup", "it", "this"):
        return None

    round_ = ROUND.search(rest)
    return {
        "company": company,
        "amount": clean_text(amount.group(0)),
        "round": round_.group(1).title() if round_ else "",
    }


def _feed_items(xml_text):
    """(title, link, published datetime | None) for each RSS item."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            published = None
        if title and link:
            items.append((title, link, published))
    return items


def fetch_funding_leads():
    cutoff = _now() - timedelta(days=FUNDING_MAX_AGE_DAYS)
    leads = {}

    for feed_url in NEWS_FEEDS:
        try:
            xml_text = get_text(
                feed_url, retries=1,
                headers={"Accept": "application/rss+xml, application/xml, text/xml"},
            )
        except Exception as error:  # noqa: BLE001
            print(f"  [leads] feed not reachable ({feed_url.split('/')[2]}): {error}")
            continue

        for title, link, published in _feed_items(xml_text):
            if published and published < cutoff:
                continue
            parsed = parse_funding_headline(title)
            if not parsed:
                continue
            lead_id = f"fund:{_slug(parsed['company'])}"
            if lead_id in leads:
                continue
            detail = " · ".join(
                part for part in (parsed["amount"], parsed["round"]) if part
            )
            leads[lead_id] = {
                "id": lead_id,
                "kind": "funding",
                "name": parsed["company"],
                "about": clean_text(re.sub(r"\s+[-–|]\s+[^-–|]{2,40}$", "", title)),
                "website": "",
                "url": link,
                "location": "",
                "team_size": 0,
                "detail": f"Raised {detail}",
                "published": published.date().isoformat() if published else "",
            }

    return list(leads.values())


# ----------------------------------------------------------------------
# Refresh
# ----------------------------------------------------------------------

def refresh(path=LEADS_FILE):
    """Merge fresh leads into leads.json. Returns the leads added this run."""
    existing = load_leads(path)
    by_id = {lead["id"]: lead for lead in existing}
    names = {lead["name"].lower() for lead in existing}
    today = _now().date().isoformat()
    added = []

    for lead in fetch_yc_leads() + fetch_funding_leads():
        if lead["id"] in by_id:
            # Keep status / first_seen; refresh the facts.
            by_id[lead["id"]].update(
                {k: v for k, v in lead.items() if k not in ("id",)}
            )
            continue
        if lead["name"].lower() in names:
            continue  # same company already known through the other feed
        lead.update({"status": "new", "first_seen": today})
        by_id[lead["id"]] = lead
        names.add(lead["name"].lower())
        added.append(lead)

    save_leads(list(by_id.values()), path)
    return added


def main():
    print("\n===================================")
    print("          COMPANY LEADS")
    print("===================================")
    added = refresh()
    total = load_leads()
    for lead in added[:40]:
        print(f"  + {lead['name']:<28} {lead['detail']}")
    if len(added) > 40:
        print(f"  ... and {len(added) - 40} more")
    print("-----------------------------------")
    print(f"  new this run  {len(added)}")
    print(f"  total leads   {len(total)}")
    print(f"  Saved → {LEADS_FILE.name}")
    print("===================================\n")


if __name__ == "__main__":
    main()
