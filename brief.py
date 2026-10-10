"""
Morning brief — the one screen to read before the day's applications.

Pulls together what the pipeline already produced:

  1. follow-ups due today            (outreach.json)
  2. new roles since yesterday       (analyses.json, best first)
  3. company leads to message        (leads.json)
  4. the manual five-minute searches (LinkedIn posts — never automated)

    python brief.py        print today's brief in the terminal

The web UI shows the same thing at /brief.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import leads as leads_mod
import outreach as outreach_mod


BASE = Path(__file__).resolve().parent
ANALYSES_FILE = BASE / "analyses.json"

NEW_WINDOW_HOURS = 36        # "new" = first seen since yesterday morning
MAX_ROLES = 8
MAX_LEADS = 5
WEEKLY_OUTREACH_TARGET = 25

WORTH_A_LOOK = ("APPLY ASAP", "APPLY", "CONSIDER")

# Founders post "we're hiring an intern" as a normal post, where the bots
# are not. LinkedIn must stay manual: scraping or auto-messaging gets
# accounts restricted. These just open the right search, newest first.
LINKEDIN_SEARCHES = [
    "hiring software intern Bangalore",
    "looking for interns full stack",
    "hiring SDE intern India",
    "PES University software engineer",
]


def _linkedin_links():
    return [
        {
            "label": query,
            "url": "https://www.linkedin.com/search/results/content/?keywords="
                   + quote(query) + "&sortBy=%22date_posted%22",
        }
        for query in LINKEDIN_SEARCHES
    ]


def _load_analyses(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in data if isinstance(item, dict)]


def _found_at(analysis):
    try:
        return datetime.fromisoformat((analysis.get("_job") or {}).get("found_at"))
    except (TypeError, ValueError):
        return None


def new_roles(now=None, analyses_path=ANALYSES_FILE, crm_jobs_by_url=None):
    """
    Roles first seen in the last NEW_WINDOW_HOURS that are worth a look,
    best first. Watchlist roles rank above job-board roles at the same
    score band: far fewer people see a careers page than a portal.

    crm_jobs_by_url (optional): {url: crm row} from the web UI, used to
    drop roles already applied to and to link to the job page.
    """
    now = now or datetime.now()
    since = now - timedelta(hours=NEW_WINDOW_HOURS)
    crm_jobs_by_url = crm_jobs_by_url or {}
    roles = []

    for analysis in _load_analyses(analyses_path):
        if analysis.get("recommendation") not in WORTH_A_LOOK:
            continue
        found = _found_at(analysis)
        if not found or found < since:
            continue

        job = analysis.get("_job") or {}
        url = job.get("url") or analysis.get("job_url") or ""
        crm = crm_jobs_by_url.get(url) or {}
        if crm.get("applied"):
            continue

        roles.append({
            "company": analysis.get("company") or job.get("company") or "",
            "role": analysis.get("role") or job.get("title") or "",
            "location": analysis.get("location") or job.get("location") or "",
            "url": url,
            "source": job.get("source") or "",
            "from_watchlist": job.get("source") == "watchlist",
            "score": (analysis.get("scores") or {}).get("overall_score") or 0,
            "recommendation": analysis.get("recommendation"),
            "job_key": crm.get("job_key") or "",
            "has_kit": bool(crm.get("kit_folder")),
        })

    roles.sort(key=lambda r: (
        WORTH_A_LOOK.index(r["recommendation"]),
        not r["from_watchlist"],
        -r["score"],
    ))
    return roles


def lead_queue():
    """Uncontacted leads: this week's funding news first, then small YC teams."""
    fresh = [l for l in leads_mod.load_leads() if l.get("status", "new") == "new"]
    fresh.sort(key=lambda l: (
        l.get("kind") != "funding",
        "" if l.get("kind") != "funding" else _reverse(l.get("first_seen", "")),
        l.get("team_size") or 9999,
    ))
    return fresh


def _reverse(iso_day):
    # Sort key that puts the most recent ISO date first.
    return "".join(chr(255 - ord(ch)) for ch in iso_day)


def build(now=None, crm_jobs_by_url=None):
    now = now or datetime.now()
    today = now.date()
    roles = new_roles(now, crm_jobs_by_url=crm_jobs_by_url)
    queue = lead_queue()
    sent = outreach_mod.sent_this_week(today)

    return {
        "date": today.strftime("%A, %d %B %Y"),
        "follow_ups": outreach_mod.due(today),
        "roles": roles[:MAX_ROLES],
        "roles_total": len(roles),
        "leads": queue[:MAX_LEADS],
        "leads_total": len(queue),
        "open_outreach": outreach_mod.open_items(today),
        "linkedin": _linkedin_links(),
        "week": {"sent": sent, "target": WEEKLY_OUTREACH_TARGET},
    }


def main():
    data = build()
    print(f"\n=== MORNING BRIEF — {data['date']} ===\n")

    print(f"Follow-ups due ({len(data['follow_ups'])})")
    for item in data["follow_ups"]:
        who = f"{item['person']} @ " if item["person"] else ""
        print(f"  - {who}{item['company']} (sent {item['sent_on']})")

    print(f"\nNew roles worth a look ({data['roles_total']})")
    for role in data["roles"]:
        mark = "★" if role["from_watchlist"] else " "
        print(f"  {mark} {role['score']:>3}  {role['role']} — {role['company']}"
              f"  [{role['recommendation']}]")
        print(f"         {role['url']}")

    print(f"\nCompanies to message ({data['leads_total']} waiting)")
    for lead in data["leads"]:
        print(f"  - {lead['name']}: {lead['detail']}")
        print(f"         {lead['url']}")

    week = data["week"]
    print(f"\nOutreach this week: {week['sent']} / {week['target']}\n")


if __name__ == "__main__":
    main()
