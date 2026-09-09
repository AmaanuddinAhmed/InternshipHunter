import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

def run_step(label, script, args=None):
    print("\n" + "=" * 55)
    print(f"   {label}")
    print("=" * 55)

    cmd = [sys.executable, str(BASE / script)]
    if args:
        cmd.extend(args)

    result = subprocess.run(cmd, cwd=BASE)

    if result.returncode != 0:
        print(f"\n[!] {label} failed.")
        print("Stop: fix the error above before continuing.")
        sys.exit(result.returncode)

    print(f"\n✓ {label} completed")

def main():
    print("""
===============================================
        AMAAN INTERNSHIP ECOSYSTEM
              DAILY PIPELINE
===============================================
""")

    crm = BASE / "Amaan_Internship_Ecosystem_v2.xlsx"

    # 1. Discover jobs
    run_step("1/5  JOB HUNTER", "job_hunter.py")

    # 2. Remove irrelevant jobs
    run_step("2/5  JOB PRE-FILTER", "pipeline.py")

    # 3. Analyze only jobs that have not already been analyzed
    run_step("3/5  GEMINI ANALYSIS", "batch_analyzer.py")

    # 4. Sync AI results into the CRM
    run_step(
        "4/5  CRM IMPORT",
        "crm_importer.py",
        ["--analysis", "analyses.json", "--crm", str(crm)]
    )

    # 5. Refresh the morning dashboard
    run_step(
        "5/5  MORNING DASHBOARD",
        "dashboard.py",
        ["--crm", str(crm)]
    )

    print("""
===============================================
             PIPELINE COMPLETE
===============================================

Excel updated:
Amaan_Internship_Ecosystem_v2.xlsx

Next action:

1. Open the Excel file.
2. Go to Morning Dashboard.
3. Start with APPLY ASAP.
4. Then review APPLY.
5. Click the job title to open the posting.
6. Apply manually.
7. Record submitted applications in Applications.

===============================================
""")

if __name__ == "__main__":
    main()
