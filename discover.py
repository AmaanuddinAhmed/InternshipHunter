"""
Job discovery — runs every enabled source, merges + dedupes the results, and
writes jobs_raw.json (the same file the rest of the pipeline consumes).

Replaces the single-source job_hunter.py entrypoint. Run standalone:

    python discover.py
"""

import json
from pathlib import Path

from sources import enabled_sources
from sources.config import SEARCH_QUERIES, LOCATIONS


BASE = Path(__file__).resolve().parent
OUTPUT_FILE = BASE / "jobs_raw.json"


def dedupe(jobs):
    """De-duplicate by URL (primary identity); fall back to company+title."""
    seen_url = set()
    seen_ct = set()
    out = []

    for job in jobs:
        url = (job.get("url") or "").strip().lower()

        if url:
            if url in seen_url:
                continue
            seen_url.add(url)
        else:
            ct = (
                (job.get("company") or "").strip().lower(),
                (job.get("title") or "").strip().lower(),
            )
            if ct in seen_ct:
                continue
            seen_ct.add(ct)

        out.append(job)

    return out


def main():
    print("\n===================================")
    print("   AMAAN INTERNSHIP JOB DISCOVERY")
    print("===================================\n")

    sources = enabled_sources()

    if not sources:
        print("No sources are configured. Check your .env keys.")
        return

    all_jobs = []
    per_source = {}

    for source in sources:
        print(f"→ {source.name}")
        try:
            found = source.search(SEARCH_QUERIES, LOCATIONS)
        except Exception as error:  # noqa: BLE001 - never let one source kill the run
            print(f"  [!] {source.name} failed: {error}")
            found = []

        per_source[source.name] = len(found)
        all_jobs.extend(found)
        print(f"  found: {len(found)}")

    deduped = dedupe(all_jobs)

    OUTPUT_FILE.write_text(
        json.dumps(deduped, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n===================================")
    print("            DISCOVERY SUMMARY")
    print("===================================")
    for name, count in per_source.items():
        print(f"  {name:<14} {count}")
    print("-----------------------------------")
    print(f"  collected     {len(all_jobs)}")
    print(f"  after dedupe  {len(deduped)}")
    print(f"  Saved → {OUTPUT_FILE.name}")
    print("===================================\n")


if __name__ == "__main__":
    main()
