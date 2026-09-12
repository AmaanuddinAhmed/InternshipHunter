"""
InternshipHunter — local web UI.

A thin Flask layer over the existing pipeline (discover.py, pipeline.py,
batch_analyzer.py, apply_assist.py, crm_importer.py, dashboard.py) and
the existing Excel CRM. It does not replace either — it reads/writes the
same .xlsx file and shells out to the same scripts daily.py already runs,
just with buttons and a nicer job browser instead of scrolling Excel.

Run with:  python app.py
Then open: http://127.0.0.1:5000
"""

import json 
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import excel_data

BASE = Path(__file__).resolve().parent.parent  # project root, one level up
CRM_PATH = BASE / "Amaan_Internship_Ecosystem_v2.xlsx"
APPLICATIONS_DIR = BASE / "applications" 
# The pipeline scripts print Unicode characters (→, ✓, ✗, —) for readable
# console output. On Windows, a subprocess whose stdout is piped (as it is
# here, not a real terminal) falls back to the system code page (often
# cp1252) instead of UTF-8, which can't encode those characters and
# crashes with UnicodeEncodeError. Forcing UTF-8 on the child process
# fixes this without touching any of the pipeline scripts themselves.
SUBPROCESS_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

app = Flask(__name__)

# ----------------------------------------------------------------------
# Pipeline step registry — mirrors daily.py exactly, so "Run All" here
# behaves identically to running `python daily.py` yourself.
# ----------------------------------------------------------------------

STEPS = [
    {
        "id": "discover",
        "label": "1. Job Discovery",
        "script": "discover.py",
        "args": [],
    },
    {
        "id": "filter",
        "label": "2. Pre-Filter",
        "script": "pipeline.py",
        "args": [],
    },
    {
        "id": "analyze",
        "label": "3. AI Analysis",
        "script": "batch_analyzer.py",
        "args": [],
    },
    {
        "id": "apply_assist",
        "label": "4. Apply-Assist Kits",
        "script": "apply_assist.py",
        "args": [],
    },
    {
        "id": "crm_import",
        "label": "5. CRM Import",
        "script": "crm_importer.py",
        "args": [
            "--analysis", "analyses.json",
            "--crm", str(CRM_PATH),
            "--applications-dir", "applications",
        ],
    },
    {
        "id": "dashboard",
        "label": "6. Rebuild Dashboard",
        "script": "dashboard.py",
        "args": ["--crm", str(CRM_PATH)],
    },
]

STEP_BY_ID = {s["id"]: s for s in STEPS}

# In-memory run registry. Fine for a single-user local tool — no DB needed.
# run = {status, lines: [...], returncode, step_id, started_at}
RUNS = {}
RUNS_LOCK = threading.Lock()


def _stream_run(run_id, script, args):
    cmd = [sys.executable, str(BASE / script), *args]

    with RUNS_LOCK:
        RUNS[run_id]["status"] = "running"

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=BASE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
            env=SUBPROCESS_ENV,
        )

        for line in proc.stdout:
            with RUNS_LOCK:
                RUNS[run_id]["lines"].append(line.rstrip("\n"))

        proc.wait()

        with RUNS_LOCK:
            RUNS[run_id]["returncode"] = proc.returncode
            RUNS[run_id]["status"] = (
                "done" if proc.returncode == 0 else "failed"
            )

    except Exception as error:  # noqa: BLE001
        with RUNS_LOCK:
            RUNS[run_id]["lines"].append(f"[!] Failed to start: {error}")
            RUNS[run_id]["status"] = "failed"
            RUNS[run_id]["returncode"] = -1


def _start_run(script, args, step_id=None):
    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {
        "status": "starting",
        "lines": [],
        "returncode": None,
        "step_id": step_id,
        "started_at": datetime.now().isoformat(),
    }
    thread = threading.Thread(
        target=_stream_run, args=(run_id, script, args), daemon=True
    )
    thread.start()
    return run_id


# ----------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", steps=STEPS)


@app.route("/job/<path:job_key>")
def job_detail(job_key):
    return render_template("job_detail.html", job_key=job_key)


# ----------------------------------------------------------------------
# Data API — reads the existing Excel file, never invents data.
# ----------------------------------------------------------------------

@app.route("/api/summary")
def api_summary():
    if not CRM_PATH.exists():
        return jsonify({"error": "CRM workbook not found. Run the pipeline first."}), 404
    return jsonify(excel_data.read_summary(CRM_PATH))


@app.route("/api/jobs")
def api_jobs():
    if not CRM_PATH.exists():
        return jsonify({"error": "CRM workbook not found. Run the pipeline first."}), 404

    recommendation = request.args.get("recommendation")  # APPLY ASAP / APPLY / CONSIDER / SKIP
    apply_status = request.args.get("apply_status")       # e.g. "not_applied"
    search = request.args.get("q", "").strip().lower()

    jobs = excel_data.read_jobs(CRM_PATH, applications_dir=APPLICATIONS_DIR)

    if recommendation:
        jobs = [j for j in jobs if j["recommendation"] == recommendation]

    if apply_status == "not_applied":
        jobs = [j for j in jobs if not j["applied"]]
    elif apply_status == "applied":
        jobs = [j for j in jobs if j["applied"]]

    if search:
        jobs = [
            j for j in jobs
            if search in j["company"].lower() or search in j["role"].lower()
        ]

    return jsonify(jobs)


@app.route("/api/job/<path:job_key>")
def api_job_detail(job_key):
    job = excel_data.read_job_by_key(CRM_PATH, job_key, applications_dir=APPLICATIONS_DIR)
    if job is None:
        return jsonify({"error": "Job not found"}), 404

    kit = None
    if job.get("kit_folder"):
        kit = excel_data.read_kit(APPLICATIONS_DIR / job["kit_folder"])

    return jsonify({"job": job, "kit": kit})


@app.route("/api/job/<path:job_key>/mark_applied", methods=["POST"])
def api_mark_applied(job_key):
    body = request.get_json(silent=True) or {}
    applied = bool(body.get("applied", True))

    try:
        updated = excel_data.set_apply_status(CRM_PATH, job_key, applied)
    except excel_data.JobNotFoundError:
        return jsonify({"error": "Job not found"}), 404
    except excel_data.WorkbookLockedError:
        return jsonify({
            "error": "Couldn't save — the Excel file looks like it's open "
                     "in Excel. Close it and try again."
        }), 409

    return jsonify({"ok": True, "job": updated})


# ----------------------------------------------------------------------
# Pipeline control API
# ----------------------------------------------------------------------

@app.route("/api/run/<step_id>", methods=["POST"])
def api_run_step(step_id):
    if step_id == "all":
        # Chain all six steps sequentially in one run, stopping on failure —
        # same semantics as daily.py.
        run_id = uuid.uuid4().hex[:12]
        RUNS[run_id] = {
            "status": "starting",
            "lines": [],
            "returncode": None,
            "step_id": "all",
            "started_at": datetime.now().isoformat(),
        }
        thread = threading.Thread(
            target=_run_all_steps, args=(run_id,), daemon=True
        )
        thread.start()
        return jsonify({"run_id": run_id})

    step = STEP_BY_ID.get(step_id)
    if step is None:
        return jsonify({"error": f"Unknown step: {step_id}"}), 404

    run_id = _start_run(step["script"], step["args"], step_id=step_id)
    return jsonify({"run_id": run_id})


def _run_all_steps(run_id):
    with RUNS_LOCK:
        RUNS[run_id]["status"] = "running"

    for step in STEPS:
        with RUNS_LOCK:
            RUNS[run_id]["lines"].append(f"\n=== {step['label']} ===")

        cmd = [sys.executable, str(BASE / step["script"]), *step["args"]]

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=BASE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                env=SUBPROCESS_ENV,
            )
            for line in proc.stdout:
                with RUNS_LOCK:
                    RUNS[run_id]["lines"].append(line.rstrip("\n"))
            proc.wait()

        except Exception as error:  # noqa: BLE001
            with RUNS_LOCK:
                RUNS[run_id]["lines"].append(f"[!] Failed to start: {error}")
                RUNS[run_id]["status"] = "failed"
                RUNS[run_id]["returncode"] = -1
            return

        if proc.returncode != 0:
            with RUNS_LOCK:
                RUNS[run_id]["lines"].append(
                    f"\n[!] {step['label']} failed (exit {proc.returncode}). Stopping."
                )
                RUNS[run_id]["status"] = "failed"
                RUNS[run_id]["returncode"] = proc.returncode
            return

    with RUNS_LOCK:
        RUNS[run_id]["lines"].append("\n=== Pipeline complete ===")
        RUNS[run_id]["status"] = "done"
        RUNS[run_id]["returncode"] = 0


@app.route("/api/run/<run_id>/status")
def api_run_status(run_id):
    run = RUNS.get(run_id)
    if run is None:
        return jsonify({"error": "Unknown run_id"}), 404
    with RUNS_LOCK:
        return jsonify(dict(run))


if __name__ == "__main__":
    print(f"Project root: {BASE}")
    print(f"CRM workbook: {CRM_PATH} ({'found' if CRM_PATH.exists() else 'NOT FOUND YET'})")
    print("\nOpen http://127.0.0.1:5000 in your browser.\n")
    app.run(host="127.0.0.1", port=5000, debug=False)