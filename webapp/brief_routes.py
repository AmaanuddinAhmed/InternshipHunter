"""
Morning brief — web routes.

Kept in its own blueprint so app.py only needs two lines to enable it:

    from brief_routes import brief_bp
    app.register_blueprint(brief_bp)

Reads/writes leads.json, outreach.json and watchlist.json in the project
root. Nothing here sends a message or submits an application.
"""

import sys
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

import excel_data

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import brief  # noqa: E402
import leads  # noqa: E402
import outreach  # noqa: E402
from sources import ats  # noqa: E402

CRM_PATH = BASE / "Amaan_Internship_Ecosystem_v2.xlsx"
APPLICATIONS_DIR = BASE / "applications"

brief_bp = Blueprint("brief", __name__)


def _crm_jobs_by_url():
    """CRM rows keyed by job URL: gives the brief applied status + job links."""
    if not CRM_PATH.exists():
        return {}
    try:
        jobs = excel_data.read_jobs(CRM_PATH, applications_dir=APPLICATIONS_DIR)
    except Exception:  # noqa: BLE001 - the brief still works without the CRM
        return {}
    return {job["url"]: job for job in jobs if job.get("url")}


def _body():
    return request.get_json(silent=True) or {}


@brief_bp.route("/brief")
def brief_page():
    return render_template("brief.html")


@brief_bp.route("/api/brief")
def api_brief():
    data = brief.build(crm_jobs_by_url=_crm_jobs_by_url())
    data["watchlist"] = ats.load_watchlist()
    return jsonify(data)


# ---------------------------------------------------------------- leads

@brief_bp.route("/api/leads/refresh", methods=["POST"])
def api_leads_refresh():
    added = leads.refresh()
    return jsonify({"added": len(added)})


@brief_bp.route("/api/leads/status", methods=["POST"])
def api_lead_status():
    body = _body()
    if body.get("status") not in ("new", "contacted", "dismissed"):
        return jsonify({"error": "Unknown status"}), 400
    lead = leads.set_status(str(body.get("id") or ""), body["status"])
    if lead is None:
        return jsonify({"error": "Lead not found"}), 404
    return jsonify({"ok": True})


# ------------------------------------------------------------- outreach

@brief_bp.route("/api/outreach/draft")
def api_outreach_draft():
    return jsonify({"text": outreach.draft(
        request.args.get("company", ""),
        request.args.get("person", ""),
        kind=request.args.get("kind", "first"),
    )})


@brief_bp.route("/api/outreach", methods=["POST"])
def api_outreach_add():
    body = _body()
    company = str(body.get("company") or "").strip()
    if not company:
        return jsonify({"error": "Company is required."}), 400

    item = outreach.add(
        company,
        person=str(body.get("person") or ""),
        channel=str(body.get("channel") or "linkedin"),
        link=str(body.get("link") or ""),
        note=str(body.get("note") or ""),
        lead_id=str(body.get("lead_id") or ""),
    )
    if item["lead_id"]:
        leads.set_status(item["lead_id"], "contacted")
    return jsonify({"ok": True, "item": item})


@brief_bp.route("/api/outreach/status", methods=["POST"])
def api_outreach_status():
    body = _body()
    try:
        item = outreach.set_status(str(body.get("id") or ""), body.get("status"))
    except ValueError:
        return jsonify({"error": "Unknown status"}), 400
    if item is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"ok": True})


# ------------------------------------------------------------ watchlist

@brief_bp.route("/api/watchlist", methods=["POST"])
def api_watchlist_add():
    """Add a company by careers-page URL, or by name (board is looked up)."""
    value = str(_body().get("value") or "").strip()
    if not value:
        return jsonify({"error": "Paste a careers link or a company name."}), 400

    found = ats.detect_from_url(value)
    if found:
        kind, slug = found
        company = slug.replace("-", " ").title()
        try:
            count = len(ats.fetch_board(kind, slug))
        except Exception:  # noqa: BLE001
            return jsonify({"error": f"Could not read {kind}/{slug}."}), 404
    elif value.lower().startswith("http"):
        return jsonify({
            "error": "Only Greenhouse, Lever and Ashby careers links can be "
                     "watched. For any other page, use “Add a job I found "
                     "myself” on the dashboard."
        }), 400
    else:
        probed = ats.probe(value)
        if not probed:
            return jsonify({
                "error": f"No Greenhouse / Lever / Ashby board found for "
                         f"“{value}”. Paste their careers link instead."
            }), 404
        kind, slug, count = probed
        company = value

    ats.add_entry(company, kind, slug)
    return jsonify({
        "ok": True, "company": company, "ats": kind, "slug": slug,
        "open_roles": count,
    })
