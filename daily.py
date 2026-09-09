import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent


def run_step(name, command):
    print("\n" + "=" * 55)
    print(f"   {name}")
    print("=" * 55)

    result = subprocess.run(
        [sys.executable] + command,
        cwd=BASE_DIR
    )

    if result.returncode != 0:
        print(f"\n[!] {name} failed.")
        print("Stop: fix the error above before continuing.")
        sys.exit(result.returncode)

    print(f"\n✓ {name} completed")


def load_json(filename):
    path = BASE_DIR / filename

    if not path.exists():
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def main():

    print("""
===============================================
        AMAAN INTERNSHIP ECOSYSTEM
              DAILY PIPELINE
===============================================
""")

    start = datetime.now()

    # ------------------------------------------------
    # STEP 1 — Search the web
    # ------------------------------------------------

    run_step(
        "1/4  JOB HUNTER",
        ["job_hunter.py"]
    )

    raw_jobs = load_json("jobs_raw.json")

    # ------------------------------------------------
    # STEP 2 — Filter jobs
    # ------------------------------------------------

    run_step(
        "2/4  JOB PRE-FILTER",
        ["pipeline.py"]
    )

    filtered_jobs = load_json("jobs_filtered.json")

    # ------------------------------------------------
    # STEP 3 — AI analysis
    # ------------------------------------------------

    run_step(
        "3/4  GEMINI ANALYSIS",
        ["batch_analyzer.py"]
    )

    analyses = load_json("analyses.json")

    # ------------------------------------------------
    # STEP 4 — Import into Excel
    # ------------------------------------------------

    run_step(
        "4/4  CRM IMPORT",
        [
            "crm_importer.py",
            "--analysis",
            "analyses.json",
            "--crm",
            "Amaan_Internship_Ecosystem_v2.xlsx"
        ]
    )

    # ------------------------------------------------
    # DAILY SUMMARY
    # ------------------------------------------------

    print("""
===============================================
             DAILY JOB BRIEF
===============================================
""")

    print(f"Jobs discovered : {len(raw_jobs)}")
    print(f"Relevant jobs   : {len(filtered_jobs)}")
    print(f"AI analyses     : {len(analyses)}")

    # Count recommendations
    counts = {
        "APPLY ASAP": 0,
        "APPLY": 0,
        "CONSIDER": 0,
        "STRETCH": 0,
        "SKIP": 0
    }

    for item in analyses:
        recommendation = item.get("recommendation", "")

        if recommendation in counts:
            counts[recommendation] += 1

    print("\nRecommendations:")
    print(f"  🔥 APPLY ASAP : {counts['APPLY ASAP']}")
    print(f"  🟢 APPLY      : {counts['APPLY']}")
    print(f"  🟡 CONSIDER   : {counts['CONSIDER']}")
    print(f"  🟠 STRETCH    : {counts['STRETCH']}")
    print(f"  🔴 SKIP       : {counts['SKIP']}")

    # ------------------------------------------------
    # TOP JOBS
    # ------------------------------------------------

    ranked = []

    for item in analyses:
        scores = item.get("scores") or {}

        score = scores.get("overall_score")

        if isinstance(score, (int, float)):
            ranked.append(item)

    ranked.sort(
        key=lambda x: (x.get("scores") or {}).get("overall_score", 0),
        reverse=True
    )

    print("\nTop opportunities:")

    for i, item in enumerate(ranked[:10], start=1):

        company = item.get("company", "Unknown")
        role = item.get("role", "Unknown")

        score = (item.get("scores") or {}).get(
            "overall_score",
            "?"
        )

        recommendation = item.get(
            "recommendation",
            "UNKNOWN"
        )

        print(
            f"{i:2}. {company} — {role}"
            f" | {score} | {recommendation}"
        )

    elapsed = datetime.now() - start

    print("""
===============================================
              PIPELINE COMPLETE
===============================================
""")

    print(f"Completed in: {elapsed}")
    print("\nExcel updated:")
    print("Amaan_Internship_Ecosystem_v2.xlsx")

    print("""
Next action:

1. Open the Excel file.
2. Go to Jobs.
3. Sort/filter by Overall Score.
4. Start with APPLY ASAP.
5. Then review APPLY.
6. Apply manually for the jobs you choose.

===============================================
""")


if __name__ == "__main__":
    main()