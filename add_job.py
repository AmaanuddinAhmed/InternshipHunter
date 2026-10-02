"""
Add one job by hand — analyze it and build its application kit.

For a posting you found yourself (LinkedIn, a careers page, a referral)
that the discovery sources never saw. Give it the JD text, or just the URL
and let the full posting be fetched (Firecrawl if FIRECRAWL_API_KEY is
set, otherwise a plain fetch that works for simple pages).

    python add_job.py --url https://... --jd-file job.txt
    python add_job.py --company Acme --title "Backend Intern" --jd-file job.txt
    python add_job.py --input manual_jobs/some_job.json      (used by the web UI)

The job is appended to analyses.json like any discovered job, so the usual
CRM import + dashboard steps pick it up. Nothing is submitted anywhere.
"""

import argparse
import json
import sys
from pathlib import Path

import apply_assist
import batch_analyzer
import jd_enricher
from sources.base import Source, make_job_id


BASE_DIR = Path(__file__).resolve().parent

MIN_JD_CHARS = 200


class ManualSource(Source):
    name = "manual"


def build_job(fields):
    title = str(fields.get("title") or "").strip()
    company = str(fields.get("company") or "").strip()
    url = str(fields.get("url") or "").strip()
    description = str(fields.get("description") or "").strip()

    if url and len(description) < MIN_JD_CHARS:
        print("Fetching the posting from its URL...")
        fetched = jd_enricher.fetch_job_description(
            url, allow_plain_fallback=True
        )
        if len(fetched) > len(description):
            description = fetched

    if len(description) < MIN_JD_CHARS:
        print(
            "ERROR: no usable job description. Paste the JD text"
            + (
                "."
                if jd_enricher.is_configured()
                else ", or add FIRECRAWL_API_KEY to .env so it can be "
                     "fetched from the URL."
            )
        )
        sys.exit(1)

    job = ManualSource().normalize(
        title=title,
        company=company,
        url=url,
        location=fields.get("location") or "",
        salary=fields.get("stipend") or "",
        job_type=fields.get("type") or "",
        snippet=description[:400],
        description=description,
        origin="added by hand",
    )

    if not url:
        # The CRM is keyed on URL; give URL-less jobs a stable stand-in.
        job["job_id"] = make_job_id(
            "manual", "", f"{company}|{title}|{description[:200]}"
        )
        job["url"] = f"manual://{job['job_id']}"

    return job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="JSON file with the fields below.")
    parser.add_argument("--company", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--location", default="")
    parser.add_argument("--stipend", default="")
    parser.add_argument("--jd-file", help="Text file containing the JD.")
    parser.add_argument(
        "--no-kit", action="store_true", help="Analyze only, skip the kit."
    )
    args = parser.parse_args()

    if args.input:
        fields = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        fields = {
            "company": args.company,
            "title": args.title,
            "url": args.url,
            "location": args.location,
            "stipend": args.stipend,
            "description": (
                Path(args.jd_file).read_text(encoding="utf-8")
                if args.jd_file else ""
            ),
        }

    print("""
===================================
          ADD JOB BY HAND
===================================
""")

    job = build_job(fields)
    client = apply_assist.create_client()

    # ---------------- Analysis ----------------
    print("Analyzing against the Career Brain...")

    try:
        analysis = batch_analyzer.analyze_one(client, job)
    except Exception as error:  # noqa: BLE001
        print(f"ERROR: analysis failed: {error}")
        sys.exit(1)

    # Fill in what the user left blank from what the JD itself says.
    if not job["title"]:
        job["title"] = str(analysis.get("role") or "").strip()
    if not job["company"]:
        job["company"] = str(analysis.get("company") or "").strip()
    analysis["_job"] = job

    analyses = batch_analyzer.load_json(batch_analyzer.ANALYSES_FILE, [])
    if not isinstance(analyses, list):
        analyses = []

    # Re-adding the same job replaces its earlier analysis.
    analyses = [
        item for item in analyses
        if not (
            isinstance(item, dict)
            and batch_analyzer.get_analysis_key(item) == job["url"]
        )
    ]
    analyses.append(analysis)
    batch_analyzer.save_json(batch_analyzer.ANALYSES_FILE, analyses)

    score = (analysis.get("scores") or {}).get("overall_score")
    print(f"✓ {job['company']} — {job['title']}")
    print(f"  Score: {score} | {analysis.get('recommendation')}")

    for blocker in analysis.get("hard_blockers") or []:
        print(f"  Hard blocker: {blocker}")

    # ---------------- Kit ----------------
    if args.no_kit:
        return

    profile = apply_assist.load_json(apply_assist.PROFILE_FILE, {})
    resume = apply_assist.load_text(apply_assist.RESUME_FILE, "")

    if not profile or not resume.strip():
        print("ERROR: profile/profile.json or profile/resume_base.md is missing.")
        sys.exit(1)

    print("Generating the application kit...")

    try:
        kit = apply_assist.generate_with_retry(client, job, profile, resume)
    except Exception as error:  # noqa: BLE001
        print(f"ERROR: kit generation failed: {error}")
        sys.exit(1)

    folder = apply_assist.get_application_folder(job)
    apply_assist.save_application_kit(folder, job, kit)

    print(f"✓ application kit generated → {folder.relative_to(BASE_DIR)}")
    print("\nNothing was submitted. Review the kit before you apply.")


if __name__ == "__main__":
    main()