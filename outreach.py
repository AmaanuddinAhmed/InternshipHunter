"""
Outreach tracker — who you messaged, and who is due a follow-up.

Stored in outreach.json. Nothing here sends anything: you send the message
yourself, then log it, and it comes back in the Morning brief when the
follow-up is due.

    python outreach.py            list open outreach and what is due today
"""

import json
import uuid
from datetime import date, timedelta
from pathlib import Path

from career_brain import load_profile


BASE = Path(__file__).resolve().parent
OUTREACH_FILE = BASE / "outreach.json"

FOLLOW_UP_DAYS = 5      # first message -> follow-up
CLOSE_AFTER_DAYS = 10   # follow-up with no reply -> stop showing it

OPEN_STATUSES = ("sent", "followed_up")
ALL_STATUSES = ("sent", "followed_up", "replied", "closed")


def load_outreach(path=OUTREACH_FILE):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("id")]


def save_outreach(items, path=OUTREACH_FILE):
    Path(path).write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def add(company, person="", channel="linkedin", link="", note="",
        lead_id="", today=None, path=OUTREACH_FILE):
    today = today or date.today()
    item = {
        "id": uuid.uuid4().hex[:10],
        "company": company.strip(),
        "person": person.strip(),
        "channel": channel.strip() or "linkedin",
        "link": link.strip(),
        "note": note.strip(),
        "lead_id": lead_id,
        "status": "sent",
        "sent_on": today.isoformat(),
        "follow_up_on": (today + timedelta(days=FOLLOW_UP_DAYS)).isoformat(),
    }
    items = load_outreach(path)
    items.append(item)
    save_outreach(items, path)
    return item


def set_status(item_id, status, today=None, path=OUTREACH_FILE):
    """sent -> followed_up -> replied / closed. Returns the item, or None."""
    if status not in ALL_STATUSES:
        raise ValueError(f"Unknown status: {status}")
    today = today or date.today()
    items = load_outreach(path)
    for item in items:
        if item["id"] == item_id:
            item["status"] = status
            if status == "followed_up":
                item["followed_up_on"] = today.isoformat()
            if status in ("replied", "closed"):
                item["closed_on"] = today.isoformat()
            save_outreach(items, path)
            return item
    return None


def due(today=None, path=OUTREACH_FILE):
    """Messages sent FOLLOW_UP_DAYS+ ago that have had no follow-up yet."""
    today = (today or date.today()).isoformat()
    return [
        item for item in load_outreach(path)
        if item["status"] == "sent" and item.get("follow_up_on", "9") <= today
    ]


def open_items(today=None, path=OUTREACH_FILE):
    """Everything still waiting on a reply, oldest first. Stale ones drop off."""
    today = today or date.today()
    stale_before = (today - timedelta(days=CLOSE_AFTER_DAYS)).isoformat()
    return sorted(
        (
            item for item in load_outreach(path)
            if item["status"] in OPEN_STATUSES
            and not (
                item["status"] == "followed_up"
                and item.get("followed_up_on", "9") < stale_before
            )
        ),
        key=lambda item: item["sent_on"],
    )


def sent_this_week(today=None, path=OUTREACH_FILE):
    today = today or date.today()
    since = (today - timedelta(days=6)).isoformat()
    return sum(1 for item in load_outreach(path) if item["sent_on"] >= since)


# ----------------------------------------------------------------------
# Message drafts — built only from profile.json, never invented.
# ----------------------------------------------------------------------

def draft(company, person="", kind="first", profile=None):
    """
    A short message to edit and send yourself. Facts come from
    profile.json; anything the profile does not have is left as a
    [bracketed] blank for you to fill, never made up.

    Optional block in profile.json:
        "outreach": {
            "availability": "full-time from January 2027",
            "proof_line": "one sentence on the best thing you have shipped",
            "portfolio": "https://..."
        }
    """
    profile = profile if profile is not None else load_profile()
    candidate = profile.get("candidate") or {}
    extra = profile.get("outreach") or {}

    greeting = f"Hi {person.split()[0]}," if person.strip() else "Hi,"
    company = company.strip() or "[company]"

    if kind == "followup":
        return (
            f"{greeting} following up on my note from last week about "
            f"interning at {company}. I know you're busy, so one line: "
            f"I can start {extra.get('availability') or '[when you can start]'} "
            "and I'm happy to do a small test task first. "
            "Would a 10-minute call work?"
        )

    study = " at ".join(
        part for part in (
            f"{candidate.get('degree', '')} student".strip(),
            candidate.get("university"),
        ) if part
    ) or "[your course and college]"

    proof = extra.get("proof_line")
    if not proof:
        experience = (profile.get("experience") or [{}])[0]
        if experience.get("role") and experience.get("company"):
            tech = ", ".join((experience.get("technologies") or [])[:4])
            proof = (
                f"I worked as a {experience['role']} at {experience['company']}"
                + (f" ({tech})" if tech else "")
            )
        else:
            proof = "[one line on the best thing you have shipped]"

    return (
        f"{greeting} I'm an {study}, available "
        f"{extra.get('availability') or '[when you are available]'}. "
        f"{proof.rstrip('.')}. "
        f"[One specific line about {company}'s product — the part only you can write.] "
        "Could I help your team as an intern? "
        f"Portfolio: {extra.get('portfolio') or '[portfolio link]'}"
    )


def main():
    today = date.today()
    waiting = open_items(today)
    due_ids = {item["id"] for item in due(today)}
    print(f"\nOpen outreach: {len(waiting)}   sent in the last 7 days: "
          f"{sent_this_week(today)}\n")
    for item in waiting:
        flag = "FOLLOW UP TODAY" if item["id"] in due_ids else item["status"]
        who = f"{item['person']} @ " if item["person"] else ""
        print(f"  [{flag:<15}] {who}{item['company']}  (sent {item['sent_on']})")
    print()


if __name__ == "__main__":
    main()
