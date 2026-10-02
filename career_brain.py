"""
Career Brain — the candidate summary the Job Analyzer scores against.

It is derived from profile/profile.json, so there is one source of truth:
uploading a new resume (setup_profile.py / the web UI) rewrites
profile.json, and the next analysis automatically uses the new brain.

If profile.json is missing or unreadable, LEGACY_CAREER_BRAIN is used so
the analyzer keeps working exactly as before.
"""

import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROFILE_FILE = BASE_DIR / "profile" / "profile.json"


LEGACY_CAREER_BRAIN = """
Candidate: Amaanuddin Ahmed
Program: MCA, PES University

Target roles:
- Full Stack Development
- Backend Development
- Software Engineering
- DevOps/Cloud
- AI-adjacent Software Engineering

Minimum stipend target: ₹25,000/month
PPO: HIGH PRIORITY

Demonstrated/relevant skills:
- JavaScript
- Node.js
- Express.js
- React.js
- MongoDB
- MERN
- Angular
- Java + DSA
- Python
- SQL/MySQL
- HTML/CSS/Bootstrap
- Git/GitHub
- REST APIs
- Authentication
- Azure / Cloud / DevOps exposure

Projects:
- StaySphere — MERN Airbnb-style application
- Zenvest — Zerodha-style application
- Contexa — context-aware people ecosystem capstone

Important:
Do not treat every technology listed here as expert-level.
Distinguish demonstrated skills from JD-only requirements.
"""


def load_profile(path=PROFILE_FILE):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _bullets(items):
    return "\n".join(f"- {item}" for item in items if str(item).strip())


def build_career_brain(profile):
    """Render profile.json as the plain-text Career Brain."""
    if not profile:
        return LEGACY_CAREER_BRAIN

    candidate = profile.get("candidate") or {}
    roles = profile.get("target_roles") or {}
    prefs = profile.get("preferences") or {}
    skills = profile.get("skills") or {}

    lines = []

    name = candidate.get("full_name") or candidate.get("name") or "Unknown"
    lines.append(f"Candidate: {name}")

    program = ", ".join(
        str(part) for part in (
            candidate.get("degree"),
            candidate.get("university"),
            candidate.get("duration"),
        ) if part
    )
    if program:
        lines.append(f"Program: {program}")
    if candidate.get("cgpa"):
        lines.append(f"CGPA: {candidate['cgpa']}")
    if candidate.get("location"):
        lines.append(f"Location: {candidate['location']}")

    if roles.get("primary"):
        lines += ["", "Target roles (primary):", _bullets(roles["primary"])]
    if roles.get("secondary"):
        lines += ["", "Target roles (secondary):", _bullets(roles["secondary"])]

    lines.append("")
    if prefs.get("minimum_stipend_inr"):
        lines.append(
            f"Minimum stipend target: ₹{prefs['minimum_stipend_inr']:,}/month"
        )
    if prefs.get("ppo_priority"):
        lines.append(f"PPO: {str(prefs['ppo_priority']).upper()} PRIORITY")
    if prefs.get("preferred_work_locations"):
        lines.append(
            "Preferred locations: "
            + ", ".join(prefs["preferred_work_locations"])
            + (" (remote also fine)" if prefs.get("remote") else "")
        )

    experience = profile.get("experience") or []
    if experience:
        lines += ["", "Work experience (real, verifiable):"]
        for item in experience:
            head = " — ".join(
                str(part) for part in (
                    item.get("role"), item.get("company"), item.get("period")
                ) if part
            )
            lines.append(f"- {head}")
            if item.get("technologies"):
                lines.append("  Tech: " + ", ".join(item["technologies"]))
            for highlight in item.get("highlights") or []:
                lines.append(f"  * {highlight}")

    if skills.get("strong"):
        lines += [
            "",
            "Skills demonstrated in work experience or projects:",
            _bullets(skills["strong"]),
        ]
    if skills.get("working"):
        lines += [
            "",
            "Skills listed on the resume but not yet demonstrated in a "
            "project or job (working knowledge only):",
            _bullets(skills["working"]),
        ]
    if skills.get("other"):
        lines += ["", "Other tools / exposure:", _bullets(skills["other"])]

    projects = profile.get("projects") or []
    if projects:
        lines += ["", "Projects:"]
        for project in projects:
            head = project.get("name", "")
            if project.get("type"):
                head += f" ({project['type']})"
            if project.get("description"):
                head += f" — {project['description']}"
            if project.get("on_resume") is False:
                head += " [in profile, not on the current resume]"
            lines.append(f"- {head}")
            if project.get("technologies"):
                lines.append("  Tech: " + ", ".join(project["technologies"]))

    if profile.get("certifications"):
        lines += ["", "Certifications:", _bullets(profile["certifications"])]

    lines += [
        "",
        "Important:",
        "Do not treat every technology listed here as expert-level.",
        "Only the 'demonstrated' skills and the work experience above count",
        "as evidence. Distinguish demonstrated skills from JD-only requirements.",
    ]

    return "\n" + "\n".join(lines) + "\n"


def load_career_brain():
    return build_career_brain(load_profile())


if __name__ == "__main__":
    print(load_career_brain())