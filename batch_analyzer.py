import argparse
import json
import os
import time
import re
from pathlib import Path

from google import genai


import analyze_job
import jd_enricher
from sources.base import identity_keys


BASE_DIR = Path(__file__).resolve().parent

FILTERED_FILE = BASE_DIR / "jobs_filtered.json"
ANALYSES_FILE = BASE_DIR / "analyses.json"

# Firecrawl second look: a job scored on a thin snippet is re-scored on the
# full posting, but only when it already looks promising, so credits are
# spent on the shortlist rather than on every listing.
ENRICH_MIN_SCORE = 60
ENRICH_MAX_PER_RUN = int(os.getenv("FIRECRAWL_MAX_PER_RUN", "40"))


def load_json(path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def get_job_key(job):
    """
    Prefer the original job URL because it is the most reliable
    identifier across daily searches.
    """
    url = str(job.get("url", "")).strip()

    if url:
        return url

    return "|".join([
        str(job.get("company", "")).strip().lower(),
        str(job.get("title", "")).strip().lower(),
        str(job.get("location", "")).strip().lower()
    ])


def get_analysis_key(analysis):
    """
    Extract the original job identity from the analysis.
    """
    job = analysis.get("_job") or {}

    # The original job URL wins. `job_url` is echoed back by the model and
    # can come back altered, which made that job look "new" on every run.
    url = str(
        job.get("url")
        or analysis.get("job_url")
        or ""
    ).strip()

    if url:
        return url

    return "|".join([
        str(analysis.get("company", "")).strip().lower(),
        str(analysis.get("role", "")).strip().lower(),
        str(analysis.get("location", "")).strip().lower()
    ])


def extract_retry_seconds(error):
    """
    Gemini usually tells us how long to wait in the error message.
    Example:
        Please retry in 48.16s.
    """

    text = str(error)

    match = re.search(
        r"retry in\s+([\d.]+)s",
        text,
        re.IGNORECASE
    )

    if match:
        return max(1, int(float(match.group(1))) + 2)

    # Safe fallback
    return 55


def analyze_one(client, job):
    """
    Analyze one job using the existing analyze_job.py configuration.

    Prefer the full job description when available.
    Fall back to the source snippet when the description is empty.
    """

    description = (
        str(job.get("description") or "").strip()
        or str(job.get("snippet") or "").strip()
    )

    jd = (
        f"Company: {job.get('company', '')}\n"
        f"Role: {job.get('title', '')}\n"
        f"Location: {job.get('location', '')}\n"
        f"Job Type: {job.get('type', '')}\n"
        f"Salary/Stipend: {job.get('salary', '')}\n"
        f"Source: {job.get('source', '')}\n"
        f"URL: {job.get('url', '')}\n"
        f"Updated: {job.get('updated', '')}\n\n"
        f"JOB DESCRIPTION:\n"
        f"{description}"
    )


    response = client.models.generate_content(
        model=analyze_job.MODEL,
        contents=analyze_job.PROMPT + "\n\nJOB DESCRIPTION:\n" + jd,
        config={
            "response_mime_type": "application/json",
            "response_schema": analyze_job.schema
        }
    )

    

    result = analyze_job.finalize_analysis(json.loads(response.text))

    # Preserve the original job data, and pin the URL to the real one
    # rather than whatever the model echoed back.
    result["_job"] = job

    if job.get("url"):
        result["job_url"] = job["url"]

    return result


def analyze_with_full_jd(client, job, state):
    """
    Analyze a job; if it was scored on a thin snippet, looks promising, and
    Firecrawl is configured, fetch the full posting and score it again.
    `state` carries the per-run Firecrawl budget.
    """
    result = analyze_one(client, job)

    if not jd_enricher.is_configured():
        return result

    if state["enriched"] >= ENRICH_MAX_PER_RUN:
        return result

    if not jd_enricher.is_thin(job):
        return result

    score = (result.get("scores") or {}).get("overall_score") or 0

    if score < ENRICH_MIN_SCORE or result.get("hard_blockers"):
        return result

    full_job = jd_enricher.enrich_job(job)

    if full_job is job:
        return result

    state["enriched"] += 1
    print("    ↳ full posting fetched — re-scoring on the complete JD")

    return analyze_one(client, full_job)


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reanalyze",
        action="store_true",
        help="Re-score every filtered job, e.g. after updating your resume.",
    )
    args = parser.parse_args()

    print("""
===================================
       GEMINI BATCH ANALYZER
===================================
""")

    jobs = load_json(FILTERED_FILE, [])
    analyses = load_json(ANALYSES_FILE, [])

    if not isinstance(jobs, list):
        jobs = []

    if not isinstance(analyses, list):
        analyses = []

    if args.reanalyze:
        filtered_keys = {get_job_key(job) for job in jobs}
        analyses = [
            analysis for analysis in analyses
            if isinstance(analysis, dict)
            and get_analysis_key(analysis) not in filtered_keys
        ]
        print("Re-analyzing all filtered jobs (--reanalyze).")

    # ------------------------------------------------
    # Build set of jobs already successfully analyzed
    # ------------------------------------------------

    # Compared on the shared job identity (canonical URL + company/title),
    # so a posting that shows up tomorrow under a new tracking URL is not
    # analyzed and imported a second time.
    analyzed_keys = set()

    for analysis in analyses:
        if isinstance(analysis, dict):
            analyzed_keys.add(get_analysis_key(analysis))
            analyzed_keys |= identity_keys(analysis.get("_job") or {})

    pending_jobs = []

    for job in jobs:
        keys = identity_keys(job) | {get_job_key(job)}

        if not (keys & analyzed_keys):
            pending_jobs.append(job)
            analyzed_keys |= keys

    print(f"Total filtered jobs : {len(jobs)}")
    print(f"Already analyzed    : {len(jobs) - len(pending_jobs)}")
    print(f"Remaining to analyze: {len(pending_jobs)}")

    if not pending_jobs:
        print("\nNothing new to analyze.")
        print(f"Saved → {ANALYSES_FILE.name}")
        print("===================================")
        return

    # ------------------------------------------------
    # Gemini client
    # ------------------------------------------------

    api_key = getattr(analyze_job, "API_KEY", None)

    if api_key:
        client = genai.Client(api_key=api_key)
    else:
        # This supports the common case where analyze_job.py
        # already initializes the client/environment.
        client = genai.Client()

    successful = 0
    failed = 0
    enrich_state = {"enriched": 0}

    if jd_enricher.is_configured():
        print(
            "Firecrawl: on — promising jobs with thin descriptions are "
            f"re-scored on the full posting (max {ENRICH_MAX_PER_RUN}/run)."
        )

    # ------------------------------------------------
    # Process jobs
    # ------------------------------------------------

    for index, job in enumerate(pending_jobs, start=1):

        company = job.get("company", "Unknown")
        title = job.get("title", "Unknown")

        print(
            f"[{index}/{len(pending_jobs)}] "
            f"{company} — {title}"
        )

        while True:

            try:

                result = analyze_with_full_jd(client, job, enrich_state)

                analyses.append(result)

                # IMPORTANT:
                # Save immediately after every successful job.
                save_json(ANALYSES_FILE, analyses)

                successful += 1

                score = (
                    result.get("scores") or {}
                ).get("overall_score")

                recommendation = result.get(
                    "recommendation",
                    "UNKNOWN"
                )

                print(
                    f"    ✓ analyzed | "
                    f"Score: {score} | "
                    f"{recommendation}"
                )

                break

            except Exception as error:

                error_text = str(error)

                # ------------------------------------------------
                # Rate limit
                # ------------------------------------------------

                if (
                    "429" in error_text
                    or "RESOURCE_EXHAUSTED" in error_text
                    or "quota" in error_text.lower()
                ):

                    wait_seconds = extract_retry_seconds(error)

                    print(
                        f"    ⚠ Gemini rate limit."
                    )

                    print(
                        f"    Waiting {wait_seconds}s "
                        f"before retry..."
                    )

                    time.sleep(wait_seconds)

                    print("    Retrying...")

                    continue

                # ------------------------------------------------
                # Other error
                # ------------------------------------------------

                print(
                    f"    ✗ ERROR: {error}"
                )

                failed += 1

                # Do not stop the entire batch because
                # one job failed.
                break

    # ------------------------------------------------
    # Final save
    # ------------------------------------------------

    save_json(ANALYSES_FILE, analyses)

    print("""
===================================
       BATCH ANALYSIS COMPLETE
===================================
""")

    print(f"Newly analyzed : {successful}")
    print(f"Failed         : {failed}")
    print(f"Total analyses : {len(analyses)}")
    print(f"Saved → {ANALYSES_FILE.name}")

    print("""
Important:
Successful analyses are saved immediately,
so the process can safely resume later.
===================================
""")


if __name__ == "__main__":
    main()
