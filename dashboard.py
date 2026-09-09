import argparse
from datetime import date, datetime
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

KEEP = {"APPLY ASAP", "APPLY", "CONSIDER"}

def real_rows(ws):
    for row in ws.iter_rows(min_row=2, values_only=True):
        if any(v not in (None, "") for v in row):
            yield row

def build_dashboard(path):
    wb = load_workbook(path)
    jobs = wb["Jobs"]
    apps = wb["Applications"]

    headers = {str(c.value).strip(): i for i, c in enumerate(jobs[1], start=0) if c.value}
    app_headers = {str(c.value).strip(): i for i, c in enumerate(apps[1], start=0) if c.value}

    def g(row, name):
        i = headers.get(name)
        return row[i] if i is not None and i < len(row) else None

    applied_ids = set()
    for row in real_rows(apps):
        jid = row[app_headers["Job ID"]] if "Job ID" in app_headers else None
        if jid:
            applied_ids.add(str(jid).strip())

    records = []
    for row in real_rows(jobs):
        jid = g(row, "Job ID")
        rec = str(g(row, "Recommendation") or "").strip().upper()
        score = g(row, "Match Score")
        if jid is None or rec not in KEEP:
            continue
        try:
            score_num = float(score)
        except (TypeError, ValueError):
            score_num = -1

        records.append({
            "job_id": str(jid),
            "company": g(row, "Company") or "",
            "role": g(row, "Role") or "",
            "url": g(row, "Job URL") or "",
            "location": g(row, "Location") or "",
            "work_mode": g(row, "Work Mode") or "",
            "stipend": g(row, "Stipend") or "",
            "ppo": g(row, "PPO Status") or g(row, "PPO Signal") or "",
            "score": score_num,
            "priority": g(row, "Priority") or "",
            "recommendation": rec,
            "resume": g(row, "Resume Version") or "",
            "date_found": g(row, "Date Found") or "",
            "applied": str(jid).strip() in applied_ids,
        })

    records.sort(key=lambda x: (x["applied"], -x["score"]))

    if "Morning Dashboard" in wb.sheetnames:
        del wb["Morning Dashboard"]
    ws = wb.create_sheet("Morning Dashboard", 0)

    # Title
    ws["A1"] = "AMAAN INTERNSHIP ECOSYSTEM — MORNING DASHBOARD"
    ws["A1"].font = Font(size=18, bold=True)
    ws.merge_cells("A1:K1")

    ws["A2"] = f"Updated: {date.today().isoformat()}"
    ws["A3"] = "Workflow: Discover → Analyze → Shortlist → Apply → Track"
    ws.merge_cells("A3:K3")

    total = len([r for r in real_rows(jobs)])
    shortlist = sum(1 for r in records if not r["applied"])
    asap = sum(1 for r in records if r["recommendation"] == "APPLY ASAP" and not r["applied"])
    apply_count = sum(1 for r in records if r["recommendation"] == "APPLY" and not r["applied"])

    stats = [
        ("Relevant/Tracked Jobs", total),
        ("Ready to Review", shortlist),
        ("APPLY ASAP", asap),
        ("APPLY", apply_count),
    ]
    for col, (label, value) in enumerate(stats, start=1):
        ws.cell(5, col, label).font = Font(bold=True)
        ws.cell(6, col, value).font = Font(size=14, bold=True)

    start = 9
    cols = ["Rank","Company","Role","Score","Recommendation","Location","Work Mode",
            "Stipend","PPO","Resume","Application Status"]
    for c, name in enumerate(cols, start=1):
        cell = ws.cell(start, c, name)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    thin = Side(style="thin")
    for r_idx, item in enumerate(records, start=start+1):
        values = [
            r_idx-start,
            item["company"],
            item["role"],
            item["score"] if item["score"] >= 0 else "",
            item["recommendation"],
            item["location"],
            item["work_mode"],
            item["stipend"],
            item["ppo"],
            item["resume"],
            "APPLIED" if item["applied"] else "NOT APPLIED",
        ]
        for c, value in enumerate(values, start=1):
            ws.cell(r_idx, c, value)
            ws.cell(r_idx, c).alignment = Alignment(vertical="top", wrap_text=True)

        if item["url"]:
            ws.cell(r_idx, 3).hyperlink = item["url"]
            ws.cell(r_idx, 3).style = "Hyperlink"

        # Make the row visually actionable.
        fill = PatternFill(fill_type="solid", fgColor="FFF2CC" if item["recommendation"] == "APPLY ASAP"
                           else "E2F0D9" if item["recommendation"] == "APPLY"
                           else "FCE4D6")
        for c in range(1, len(cols)+1):
            ws.cell(r_idx, c).fill = fill

    # Add a direct Job URL column after Role via a second compact table isn't necessary;
    # the Role cell itself is clickable. Add instruction.
    ws["A7"] = "Tip:"
    ws["A7"].font = Font(bold=True)
    ws["B7"] = "Click the Role to open the job. Apply manually, then record it in Applications."
    ws.merge_cells("B7:K7")

    # Widths
    widths = [7, 28, 42, 9, 16, 16, 14, 20, 18, 36, 18]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    ws.freeze_panes = "A10"
    ws.auto_filter.ref = f"A{start}:K{start+max(1,len(records))}"

    # Add a tiny "how to use" area
    help_row = start + len(records) + 3
    ws.cell(help_row, 1, "MORNING ROUTINE").font = Font(bold=True, size=12)
    steps = [
        "1. Start with APPLY ASAP.",
        "2. Open the job by clicking its Role.",
        "3. Apply manually if you want to proceed.",
        "4. Add the application to the Applications sheet.",
        "5. Run daily.py tomorrow; the dashboard will move applied jobs out of the action list.",
    ]
    for i, text in enumerate(steps, start=help_row+1):
        ws.cell(i, 1, text)
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=11)

    # Refresh Analytics-style quick counts if the sheet exists.
    if "Analytics" in wb.sheetnames:
        a = wb["Analytics"]
        a["B2"] = total
        a["B3"] = sum(1 for r in records)
        a["B4"] = sum(1 for r in real_rows(apps))
        a["B6"] = 0  # Offers can continue to be tracked manually.
        a["B7"] = 0

    wb.save(path)
    print(f"Dashboard refreshed → {path}")
    print(f"Actionable jobs: {shortlist} | APPLY ASAP: {asap} | APPLY: {apply_count}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--crm", default="Amaan_Internship_Ecosystem_v2.xlsx")
    args = ap.parse_args()
    build_dashboard(Path(args.crm))
