import argparse
import json
from datetime import date
from pathlib import Path

from openpyxl import load_workbook


def s(v):
    if v is None:
        return ""

    if isinstance(v, list):
        return "; ".join(
            json.dumps(x, ensure_ascii=False)
            if isinstance(x, dict)
            else str(x)
            for x in v
        )

    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)

    return str(v)


def get_next_row(ws):
    row = ws.max_row

    while row > 1:
        if any(
            ws.cell(row, c).value
            for c in range(1, ws.max_column + 1)
        ):
            break
        row -= 1

    return row + 1


def main():

    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--analysis",
        required=True
    )

    ap.add_argument(
        "--crm",
        required=True
    )

    args = ap.parse_args()

    # --------------------------------------------------
    # LOAD ANALYSIS
    # --------------------------------------------------

    data = json.loads(
        Path(args.analysis).read_text(
            encoding="utf-8"
        )
    )

    # Support both:
    # { ... }
    # and
    # [ {...}, {...} ]

    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        raise ValueError(
            "Analysis file must contain an object or list of objects."
        )

    # --------------------------------------------------
    # LOAD WORKBOOK
    # --------------------------------------------------

    wb = load_workbook(args.crm)

    ws = wb["Jobs"]

    # --------------------------------------------------
    # READ HEADERS
    # --------------------------------------------------

    headers = {
        ws.cell(1, c).value: c
        for c in range(1, ws.max_column + 1)
        if ws.cell(1, c).value
    }

    # --------------------------------------------------
    # FIND EXISTING JOBS BY URL
    # --------------------------------------------------

    url_col = headers.get("Job URL")

    if not url_col:
        raise ValueError(
            "Could not find 'Job URL' column in Jobs sheet."
        )

    existing_by_url = {}

    for row in range(2, ws.max_row + 1):

        value = ws.cell(row, url_col).value

        if value:
            existing_by_url[str(value).strip()] = row

    # --------------------------------------------------
    # PROCESS
    # --------------------------------------------------

    imported = 0
    updated = 0
    skipped = 0

    target = get_next_row(ws)

    for item in data:

        if not isinstance(item, dict):
            continue

        company = s(item.get("company"))
        role = s(item.get("role"))
        job_url = s(item.get("job_url"))

        if not job_url:
            skipped += 1
            continue

        # --------------------------------------------------
        # NESTED DATA
        # --------------------------------------------------

        stipend = item.get("stipend") or {}
        ppo = item.get("ppo") or {}
        eligibility = item.get("eligibility") or {}
        availability = item.get("availability") or {}
        scores = item.get("scores") or {}
        reasoning = item.get("reasoning") or {}

        overall_score = scores.get("overall_score")

        # --------------------------------------------------
        # DETERMINE ROW
        # --------------------------------------------------

        if job_url in existing_by_url:

            row_number = existing_by_url[job_url]

            updated += 1

            action = "Updated"

        else:

            row_number = target

            target += 1

            imported += 1

            # Job ID
            job_id = (
                f"{company[:12].upper().replace(' ', '-')}"
                f"-{date.today():%y%m%d}"
                f"-{imported}"
            )

            if "Job ID" in headers:
                ws.cell(
                    row_number,
                    headers["Job ID"]
                ).value = job_id

            action = "Imported"

        # --------------------------------------------------
        # VALUES TO WRITE
        # --------------------------------------------------

        values = {

            "Company":
                company,

            "Role":
                role,

            "Job URL":
                job_url,

            "Source":
                "AI Analyzer",

            "Location":
                s(item.get("location")),

            "Work Mode":
                s(item.get("work_mode")),

            "Job Type":
                s(item.get("job_type")),

            "Stipend":
                s(stipend.get("raw")),

            "Duration":
                s(item.get("duration")),

            "PPO Signal":
                s(ppo.get("status")),

            "Required Skills":
                s(item.get("required_skills")),

            "Preferred Skills":
                s(item.get("preferred_skills")),

            "JD Text":
                s(
                    (item.get("_job") or {}).get(
                        "snippet"
                    )
                ),

            # IMPORTANT:
            # Gemini overall_score -> existing CRM Match Score
            "Match Score":
                overall_score,

            "Technical Fit":
                scores.get("technical_fit"),

            "Experience Fit":
                scores.get("experience_fit"),

            "Role Fit":
                scores.get("role_fit"),

            "PPO Score":
                scores.get("ppo_score"),

            "Compensation Fit":
                scores.get("compensation_fit"),

            "Opportunity Quality":
                scores.get("opportunity_quality"),

            "Priority":
                s(item.get("recommendation")),

            "Recommendation":
                s(item.get("recommendation")),

            "Skill Gaps":
                s(item.get("skill_gaps")),

            "Resume Version":
                s(item.get("recommended_resume")),

            "Date Found":
                date.today().isoformat(),

            "Notes":
                s(
                    (reasoning.get("why_apply") or [])
                ),

            "Eligibility Status":
                s(eligibility.get("status")),

            "Eligibility Reasons":
                s(eligibility.get("reasons")),

            "Availability Status":
                s(availability.get("status")),

            "Availability Reason":
                s(availability.get("reason")),

            "Compensation Status":
                s(stipend.get("status")),

            "Guaranteed Stipend":
                stipend.get("guaranteed_min_inr"),

            "Incentive Included":
                (
                    "Yes"
                    if stipend.get(
                        "incentive_included"
                    )
                    else "No"
                ),

            "PPO Status":
                s(ppo.get("status")),

            "PPO Evidence":
                s(ppo.get("evidence")),

            "Hard Blockers":
                s(item.get("hard_blockers")),

            "Red Flags":
                s(item.get("red_flags")),

            "Interview Topics":
                s(item.get("interview_topics")),
        }

        # --------------------------------------------------
        # WRITE VALUES
        # --------------------------------------------------

        for header, value in values.items():

            if header in headers:

                ws.cell(
                    row_number,
                    headers[header]
                ).value = value

        # Remember URL -> row
        existing_by_url[job_url] = row_number

        print(
            f"{action}: {company} — {role}"
            f" | Score: {overall_score}"
        )

    # --------------------------------------------------
    # SAVE
    # --------------------------------------------------

    try:

        wb.save(args.crm)

    except PermissionError:

        print(
            "\n[!] Permission Error:"
            f" '{args.crm}' is currently open."
        )

        print(
            "Close Excel and run the command again."
        )

        return

    # --------------------------------------------------
    # SUMMARY
    # --------------------------------------------------

    print()
    print("===================================")
    print(f"New jobs imported : {imported}")
    print(f"Existing jobs updated : {updated}")
    print(f"Skipped : {skipped}")
    print(f"Analyses processed : {len(data)}")
    print(f"Saved → {args.crm}")
    print("===================================")


if __name__ == "__main__":
    main()