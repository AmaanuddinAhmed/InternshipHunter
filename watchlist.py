"""
Manage the company watchlist (watchlist.json).

    python watchlist.py                     list the watchlist
    python watchlist.py add <careers-url>   add from a Greenhouse / Lever / Ashby link
    python watchlist.py probe "Name" ...    find a board by company name and add it
    python watchlist.py probe --leads       try every company in leads.json
    python watchlist.py check               test every entry, show open-job counts

`probe` guesses the board address from the name. A guess can land on a
different company with a similar name, so check the printed job count and
link once before trusting a new entry.
"""

import argparse
import sys

from sources import ats


BOARD_URL = {
    "greenhouse": "https://boards.greenhouse.io/{}",
    "lever": "https://jobs.lever.co/{}",
    "ashby": "https://jobs.ashbyhq.com/{}",
}


def cmd_list(_args):
    entries = ats.load_watchlist()
    if not entries:
        print("Watchlist is empty. Add one: python watchlist.py probe \"Company\"")
        return
    for entry in entries:
        state = "" if entry.get("enabled", True) else "  (disabled)"
        print(f"  {entry['company']:<28} {entry['ats']:<11} {entry['slug']}{state}")
    print(f"\n{len(entries)} companies watched.")


def cmd_add(args):
    found = ats.detect_from_url(args.url)
    if not found:
        print("That is not a Greenhouse, Lever or Ashby careers link.")
        print("Try: python watchlist.py probe \"Company name\"")
        sys.exit(1)
    kind, slug = found
    try:
        jobs = ats.fetch_board(kind, slug)
    except Exception as error:  # noqa: BLE001
        print(f"Could not read {kind}/{slug}: {error}")
        sys.exit(1)
    company = args.name or slug.replace("-", " ").title()
    ats.add_entry(company, kind, slug)
    print(f"Added {company} ({kind}/{slug}) — {len(jobs)} open roles.")


def _probe_one(name, website=""):
    found = ats.probe(name, website)
    if not found:
        print(f"  ✗ {name}: no Greenhouse / Lever / Ashby board found")
        return False
    kind, slug, count = found
    ats.add_entry(name, kind, slug)
    print(f"  ✓ {name}: {count} open roles — {BOARD_URL[kind].format(slug)}")
    return True


def cmd_probe(args):
    targets = [(name, "") for name in args.names]

    if args.leads:
        import leads
        watched = {e["company"].lower() for e in ats.load_watchlist()}
        targets += [
            (lead["name"], lead.get("website", ""))
            for lead in leads.load_leads()
            if lead.get("status") != "dismissed"
            and lead["name"].lower() not in watched
        ]

    if not targets:
        print("Give one or more company names, or --leads.")
        sys.exit(1)

    added = sum(_probe_one(name, website) for name, website in targets)
    print(f"\nAdded {added} of {len(targets)}. Open each link once to confirm "
          "it is the right company.")


def cmd_check(_args):
    entries = ats.load_watchlist()
    dead = 0
    for entry in entries:
        try:
            count = len(ats.fetch_board(entry["ats"], entry["slug"]))
            print(f"  ✓ {entry['company']:<28} {count} open roles")
        except Exception as error:  # noqa: BLE001
            dead += 1
            print(f"  ✗ {entry['company']:<28} {entry['ats']}/{entry['slug']} — {error}")
    print(f"\n{len(entries) - dead} working, {dead} not reachable.")


def main():
    parser = argparse.ArgumentParser(description="Manage the company watchlist.")
    sub = parser.add_subparsers(dest="command")

    add = sub.add_parser("add", help="add from a careers-page URL")
    add.add_argument("url")
    add.add_argument("--name", help="company display name")

    probe = sub.add_parser("probe", help="find boards by company name")
    probe.add_argument("names", nargs="*")
    probe.add_argument("--leads", action="store_true",
                       help="also try every company in leads.json")

    sub.add_parser("check", help="test every watchlist entry")

    args = parser.parse_args()
    {"add": cmd_add, "probe": cmd_probe, "check": cmd_check}.get(
        args.command, cmd_list
    )(args)


if __name__ == "__main__":
    main()
