"""
All reading of / writing to the existing CRM workbook lives here, kept
separate from Flask routing so the Excel-specific logic is easy to find
and test on its own.

This module never restructures the workbook — it only reads the Jobs /
Morning Dashboard sheets and, for "mark applied", updates one existing
column (Jobs!Apply Status) and appends one row to Applications. It does
not touch anything dashboard.py or crm_importer.py already own.
"""

import json
import zipfile
from datetime import datetime
from pathlib import Path

import openpyxl


JOBS_SHEET = "Jobs"
APPLICATIONS_SHEET = "Applications"
DASHBOARD_SHEET = "Morning Dashboard"

# Column positions on the Jobs sheet (1-indexed, matches crm_importer.py's
# header order). Looked up by header name at load time as a safety net in
# case a column ever gets reordered.
JOBS_KEY_HEADERS = {
    "job_id": "Job ID",
    "company": "Company",
    "role": "Role",
    "url": "Job URL",
    "source": "Source",
    "location": "Location",
    "work_mode": "Work Mode",
    "stipend": "Stipend",
    "duration": "Duration",
    "ppo_signal": "PPO Signal",
    "match_score": "Match Score",
    "priority": "Priority",
    "recommendation": "Recommendation",
    "date_found": "Date Found",
    "eligibility_status": "Eligibility Status",
    "availability_status": "Availability Status",
    "compensation_status": "Compensation Status",
    "ppo_status": "PPO Status",
    "hard_blockers": "Hard Blockers",
    "red_flags": "Red Flags",
    "kit_path": "Application Kit Path",
    "kit_status": "Application Kit Status",
    "apply_status": "Apply Status",
}

APPLICATIONS_HEADERS = [
    "Application ID", "Job ID", "Company", "Role", "Job URL",
    "Resume Version", "Applied Date", "Status", "Next Action",
    "Follow-up Date", "Application Notes", "OA Date", "Interview Date",
    "Outcome", "Stipend", "PPO", "Days Since Applied",
]


class JobNotFoundError(Exception):
    pass


class WorkbookLockedError(Exception):
    pass


def _header_index(ws):
    """Map header name -> 1-indexed column number, from row 1."""
    return {
        str(cell.value).strip(): cell.column
        for cell in ws[1]
        if cell.value
    }


def _col(headers, key):
    name = JOBS_KEY_HEADERS[key]
    col = headers.get(name)
    if col is None:
        raise KeyError(f"Expected column '{name}' not found in Jobs sheet")
    return col


def _kit_folder_from_path(raw_path):
    """
    Application Kit Path is stored as an absolute path from whatever
    machine generated it (e.g. 'E:\\...\\applications\\6509...'). We only
    need the trailing folder name (the job_id) and resolve it against
    *this* machine's applications/ directory, so kit links work
    regardless of which machine wrote the workbook.
    """
    if not raw_path:
        return None
    raw_path = str(raw_path).strip()
    if not raw_path:
        return None
    # Handle both \ and / as separators regardless of host OS.
    normalized = raw_path.replace("\\", "/")
    return normalized.rstrip("/").rsplit("/", 1)[-1]


def _safe_str(value):
    return "" if value is None else str(value).strip()


def _safe_num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_summary(crm_path):
    wb = openpyxl.load_workbook(crm_path, data_only=True)
    ws = wb[DASHBOARD_SHEET]

    # The Morning Dashboard's summary numbers sit in a small fixed block
    # near the top (see dashboard.py): a label row followed by a value
    # row. We scan for it defensively rather than hardcoding row numbers,
    # since dashboard.py may add columns over time.
    labels = ["Relevant/Tracked Jobs", "Apply Queue", "APPLY ASAP", "APPLY", "Kits Ready", "Applied"]
    result = {label: None for label in labels}

    for row in ws.iter_rows(min_row=1, max_row=15):
        row_values = [c.value for c in row]
        if any(v in labels for v in row_values):
            value_row = row[0].row + 1
            for cell in row:
                if cell.value in labels:
                    val_cell = ws.cell(value_row, cell.column)
                    result[cell.value] = val_cell.value
            break

    updated_at = None
    for row in ws.iter_rows(min_row=1, max_row=5, max_col=1):
        val = row[0].value
        if val and "Updated" in str(val):
            updated_at = str(val).replace("Updated:", "").strip()
            break

    return {
        "tracked_jobs": result.get("Relevant/Tracked Jobs"),
        "apply_queue": result.get("Apply Queue"),
        "apply_asap": result.get("APPLY ASAP"),
        "apply": result.get("APPLY"),
        "kits_ready": result.get("Kits Ready"),
        "applied": result.get("Applied"),
        "updated_at": updated_at,
    }


def _row_to_job(headers, row_cells, applications_dir):
    def get(key):
        col = headers.get(JOBS_KEY_HEADERS[key])
        if col is None:
            return None
        return row_cells[col - 1]

    url = _safe_str(get("url"))
    job_id = _safe_str(get("job_id"))

    kit_folder = _kit_folder_from_path(get("kit_path"))
    kit_exists = False
    if kit_folder:
        kit_exists = (applications_dir / kit_folder / "application_kit.json").exists()

    apply_status = _safe_str(get("apply_status"))

    return {
        # job_key is what the UI/API uses to address this job. Prefer
        # Job ID (stable, short); fall back to URL if ID is missing.
        "job_key": job_id or url,
        "job_id": job_id,
        "url": url,
        "company": _safe_str(get("company")),
        "role": _safe_str(get("role")),
        "source": _safe_str(get("source")),
        "location": _safe_str(get("location")),
        "work_mode": _safe_str(get("work_mode")),
        "stipend": _safe_str(get("stipend")),
        "duration": _safe_str(get("duration")),
        "ppo_signal": _safe_str(get("ppo_signal")),
        "match_score": _safe_num(get("match_score")),
        "priority": _safe_str(get("priority")),
        "recommendation": _safe_str(get("recommendation")),
        "date_found": _safe_str(get("date_found")),
        "eligibility_status": _safe_str(get("eligibility_status")),
        "availability_status": _safe_str(get("availability_status")),
        "compensation_status": _safe_str(get("compensation_status")),
        "ppo_status": _safe_str(get("ppo_status")),
        "hard_blockers": _safe_str(get("hard_blockers")),
        "red_flags": _safe_str(get("red_flags")),
        "kit_folder": kit_folder if kit_exists else None,
        "kit_status": _safe_str(get("kit_status")),
        "apply_status": apply_status,
        "applied": apply_status.lower() not in ("", "ready to apply"),
    }


def read_jobs(crm_path, applications_dir):
    wb = openpyxl.load_workbook(crm_path, data_only=True)
    ws = wb[JOBS_SHEET]
    headers = _header_index(ws)

    jobs = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(row):
            continue
        job = _row_to_job(headers, row, applications_dir)
        if not job["company"] and not job["role"]:
            continue
        jobs.append(job)

    # Highest-scoring / most-recommended first, matching the dashboard's
    # own ordering intent.
    priority_rank = {"APPLY ASAP": 0, "APPLY": 1, "CONSIDER": 2, "SKIP": 3}
    jobs.sort(
        key=lambda j: (
            priority_rank.get(j["recommendation"], 4),
            -(j["match_score"] or 0),
        )
    )

    return jobs


def read_job_by_key(crm_path, job_key, applications_dir):
    for job in read_jobs(crm_path, applications_dir):
        if job["job_key"] == job_key:
            return job
    return None


def read_kit(kit_folder_path):
    kit_json = kit_folder_path / "application_kit.json"
    if not kit_json.exists():
        return None

    try:
        data = json.loads(kit_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    kit = data.get("kit", {})

    def read_md(name):
        path = kit_folder_path / name
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                return None
        return None

    return {
        "generated_at": data.get("generated_at"),
        "status": data.get("status"),
        "resume_bullets": kit.get("tailored_resume_bullets", []),
        "cover_letter": kit.get("cover_letter") or read_md("cover_letter.md"),
        "screening_answers": kit.get("screening_answers", {}),
        "skills_to_highlight": kit.get("skills_to_highlight", []),
        "skill_gaps": kit.get("skill_gaps", []),
        "application_strategy": kit.get("application_strategy", []),
        "confidence": kit.get("confidence"),
    }


def set_apply_status(crm_path, job_key, applied):
    """
    Update Jobs!Apply Status for the row matching job_key (Job ID or Job
    URL), and append a row to Applications if marking as applied. Saves
    in place. Raises JobNotFoundError / WorkbookLockedError as needed.
    """
    try:
        wb = openpyxl.load_workbook(crm_path, data_only=False)
    except PermissionError as error:
        raise WorkbookLockedError(str(error)) from error

    ws = wb[JOBS_SHEET]
    headers = _header_index(ws)

    id_col = _col(headers, "job_id")
    url_col = _col(headers, "url")
    company_col = _col(headers, "company")
    role_col = _col(headers, "role")
    resume_col = headers.get("Resume Version")
    stipend_col = _col(headers, "stipend")
    ppo_col = _col(headers, "ppo_signal")
    apply_status_col = _col(headers, "apply_status")

    target_row = None
    row_data = None

    for row in ws.iter_rows(min_row=2):
        job_id_val = _safe_str(row[id_col - 1].value)
        url_val = _safe_str(row[url_col - 1].value)
        if job_key and (job_key == job_id_val or job_key == url_val):
            target_row = row
            row_data = row
            break

    if target_row is None:
        raise JobNotFoundError(job_key)

    new_status = "Applied" if applied else "Ready to Apply"
    ws.cell(target_row[0].row, apply_status_col).value = new_status

    if applied:
        _append_application_row(
            wb,
            job_id=_safe_str(row_data[id_col - 1].value),
            company=_safe_str(row_data[company_col - 1].value),
            role=_safe_str(row_data[role_col - 1].value),
            url=_safe_str(row_data[url_col - 1].value),
            resume=_safe_str(row_data[resume_col - 1].value) if resume_col else "",
            stipend=_safe_str(row_data[stipend_col - 1].value),
            ppo=_safe_str(row_data[ppo_col - 1].value),
        )

    try:
        wb.save(crm_path)
    except PermissionError as error:
        raise WorkbookLockedError(str(error)) from error

    return {
        "job_key": job_key,
        "apply_status": new_status,
        "applied": applied,
    }


def _append_application_row(wb, *, job_id, company, role, url, resume, stipend, ppo):
    if APPLICATIONS_SHEET not in wb.sheetnames:
        return

    ws = wb[APPLICATIONS_SHEET]
    headers = _header_index(ws)

    # Find the first row that has no real application data yet. The
    # "Days Since Applied" column holds a formula on every pre-formatted
    # row (e.g. =IF(G2="","",TODAY()-G2)), so a truly-empty row still has
    # a non-empty cell there — check the data columns only, not formulas.
    data_columns = [
        headers.get(name)
        for name in ("Application ID", "Job ID", "Company", "Role")
        if headers.get(name)
    ]

    insert_row = ws.max_row + 1
    for row in ws.iter_rows(min_row=2):
        row_by_col = {c.column: c.value for c in row}
        if all(not row_by_col.get(col) for col in data_columns):
            insert_row = row[0].row
            break

    def set_val(header_name, value):
        col = headers.get(header_name)
        if col:
            ws.cell(insert_row, col).value = value

    application_id = f"APP-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    set_val("Application ID", application_id)
    set_val("Job ID", job_id)
    set_val("Company", company)
    set_val("Role", role)
    set_val("Job URL", url)
    set_val("Resume Version", resume)
    set_val("Applied Date", datetime.now().strftime("%Y-%m-%d"))
    set_val("Status", "Applied")
    set_val("Stipend", stipend)
    set_val("PPO", ppo)