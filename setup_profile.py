"""
Update the candidate profile from a resume.

    python setup_profile.py --resume path/to/resume.pdf
    python setup_profile.py --resume resume.docx --dry-run

Reads a PDF / DOCX / Markdown / text resume, asks Gemini to structure it,
and rewrites:

    profile/profile.json     -> candidate, skills, experience, projects, ...
    profile/resume_base.md   -> the resume text every application kit uses

The Career Brain (career_brain.py) is derived from profile.json, so the
next analysis is scored against the new resume automatically.

Two safeguards, because nothing here may inflate the resume:

1. Grounding check. Every skill, technology, employer, project and bullet
   the model returns must actually be found in the resume text. Anything
   that is not is dropped and listed in the output.
2. Skills are split into "demonstrated in a job or project" and "only
   listed in the skills section", and the analyzer is told the difference.

What a resume does not contain is never touched: target roles, stipend
and location preferences, and application strategy stay as they are.
The previous files are copied to profile/backups/<timestamp>/ first.
"""

import argparse
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import analyze_job
import apply_assist
from career_brain import build_career_brain


BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "profile"
PROFILE_FILE = PROFILE_DIR / "profile.json"
RESUME_FILE = PROFILE_DIR / "resume_base.md"
BACKUP_DIR = PROFILE_DIR / "backups"

MIN_RESUME_CHARS = 300


# ============================================================
# Resume text extraction
# ============================================================

def extract_text(path):
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
        text = re.sub(r"<[^>]+>", "", xml)
        return (
            text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&apos;", "'")
        )

    if suffix in {".md", ".txt", ""}:
        return path.read_text(encoding="utf-8", errors="replace")

    raise ValueError(
        f"Unsupported resume type '{suffix}'. Use PDF, DOCX, MD or TXT."
    )


# ============================================================
# Prompt + schema
# ============================================================

PROMPT = """
You convert a resume into structured data. You are a careful transcriber,
not a writer.

RULES

1. Use ONLY what is written in the RESUME below. Never add, infer,
   upgrade or embellish anything: no extra skills, no metrics, no
   responsibilities, no seniority, no dates that are not there.
2. Copy experience and project bullet points word for word. You may only
   repair line breaks and hyphenation caused by PDF extraction.
3. Copy names (companies, projects, institutions, certifications) exactly
   as written.
4. If something is absent from the resume, return an empty string or an
   empty list for it. Do not guess.

SKILLS

- skill_groups: the resume's own skills section, with its own group
  headings and items, unchanged.
- skills_demonstrated: skills that are evidenced by at least one work
  experience or project on the resume. A stack name counts for its parts
  (a MERN project demonstrates MongoDB, Express, React and Node.js; a
  Node.js/Express project demonstrates JavaScript).
- skills_listed_only: skills that appear in the skills section but are not
  evidenced by any experience or project.
- Every skill must be spelled as it appears in the resume, and must be in
  exactly one of the two lists.

EXPERIENCE AND PROJECTS

- technologies: only technologies named in that specific entry.
- description (projects): one plain sentence saying what it is, built only
  from the resume's own words.

Return ONLY JSON matching the schema.

RESUME:
"""

_STR = {"type": "STRING"}
_STR_LIST = {"type": "ARRAY", "items": _STR}

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "candidate": {
            "type": "OBJECT",
            "properties": {
                "name": _STR,
                "location": _STR,
                "email": _STR,
                "phone": _STR,
                "degree": _STR,
                "university": _STR,
                "duration": _STR,
                "cgpa": _STR,
            },
            "required": [
                "name", "location", "email", "phone",
                "degree", "university", "duration", "cgpa",
            ],
        },
        "summary": _STR,
        "skill_groups": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"group": _STR, "items": _STR_LIST},
                "required": ["group", "items"],
            },
        },
        "skills_demonstrated": _STR_LIST,
        "skills_listed_only": _STR_LIST,
        "experience": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "role": _STR,
                    "company": _STR,
                    "period": _STR,
                    "technologies": _STR_LIST,
                    "highlights": _STR_LIST,
                },
                "required": [
                    "role", "company", "period", "technologies", "highlights",
                ],
            },
        },
        "projects": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": _STR,
                    "tagline": _STR,
                    "description": _STR,
                    "technologies": _STR_LIST,
                    "highlights": _STR_LIST,
                },
                "required": [
                    "name", "tagline", "description",
                    "technologies", "highlights",
                ],
            },
        },
        "education": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "degree": _STR,
                    "institution": _STR,
                    "period": _STR,
                    "score": _STR,
                },
                "required": ["degree", "institution", "period", "score"],
            },
        },
        "certifications": _STR_LIST,
        "achievements": _STR_LIST,
    },
    "required": [
        "candidate", "summary", "skill_groups", "skills_demonstrated",
        "skills_listed_only", "experience", "projects", "education",
        "certifications", "achievements",
    ],
}


def interpret_resume(client, resume_text):
    response = client.models.generate_content(
        model=analyze_job.MODEL,
        contents=PROMPT + resume_text,
        config={
            "response_mime_type": "application/json",
            "response_schema": SCHEMA,
        },
    )
    return json.loads(response.text)


# ============================================================
# Grounding — nothing survives that is not in the resume
# ============================================================

def _norm(text):
    return re.sub(r"[^a-z0-9+#]", "", str(text).lower())


def _term_grounded(term, haystack):
    """A short term (skill, name) appears in the resume, modulo styling."""
    key = _norm(term)
    if not key:
        return False

    variants = {key}
    if key.endswith("js") and len(key) > 4:
        variants.add(key[:-2])          # "Express.js" vs "Express"
    else:
        variants.add(key + "js")        # "React" vs "React.js"
    if key.endswith("s"):
        variants.add(key[:-1])          # "REST APIs" vs "REST API"

    return any(v and v in haystack for v in variants)


def _sentence_grounded(sentence, resume_words):
    """A bullet is grounded when nearly all its real words are in the resume."""
    words = [w for w in re.findall(r"[a-z0-9+#.]+", sentence.lower()) if len(w) > 3]
    if not words:
        return True
    hits = sum(1 for w in words if w.strip(".") in resume_words)
    return hits / len(words) >= 0.85


def ground(data, resume_text):
    """
    Remove anything not supported by the resume text.
    Returns (clean_data, list_of_removed_descriptions).
    """
    haystack = _norm(resume_text)
    resume_words = {
        w.strip(".")
        for w in re.findall(r"[a-z0-9+#.]+", resume_text.lower())
    }
    removed = []

    def keep_terms(items, label):
        kept = []
        for item in items or []:
            item = str(item).strip()
            if not item:
                continue
            if _term_grounded(item, haystack):
                if item not in kept:
                    kept.append(item)
            else:
                removed.append(f"{label}: {item}")
        return kept

    def keep_sentences(items, label):
        kept = []
        for item in items or []:
            item = re.sub(r"\s+", " ", str(item)).strip()
            if not item:
                continue
            if _sentence_grounded(item, resume_words):
                kept.append(item)
            else:
                removed.append(f"{label}: {item}")
        return kept

    data["skills_demonstrated"] = keep_terms(
        data.get("skills_demonstrated"), "skill"
    )
    data["skills_listed_only"] = [
        skill for skill in keep_terms(data.get("skills_listed_only"), "skill")
        if skill not in data["skills_demonstrated"]
    ]

    groups = []
    for group in data.get("skill_groups") or []:
        items = keep_terms(group.get("items"), "skill")
        if items:
            groups.append({"group": str(group.get("group") or "").strip(), "items": items})
    data["skill_groups"] = groups

    experience = []
    for item in data.get("experience") or []:
        company = str(item.get("company") or "").strip()
        role = str(item.get("role") or "").strip()
        if company and not _term_grounded(company, haystack):
            removed.append(f"experience (employer not found in resume): {company}")
            continue
        if not (company or role):
            continue
        item["technologies"] = keep_terms(item.get("technologies"), f"tech @ {company}")
        item["highlights"] = keep_sentences(item.get("highlights"), f"bullet @ {company}")
        experience.append(item)
    data["experience"] = experience

    projects = []
    for item in data.get("projects") or []:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if not _term_grounded(name, haystack):
            removed.append(f"project (name not found in resume): {name}")
            continue
        item["technologies"] = keep_terms(item.get("technologies"), f"tech @ {name}")
        item["highlights"] = keep_sentences(item.get("highlights"), f"bullet @ {name}")
        if item.get("description") and not _sentence_grounded(
            str(item["description"]), resume_words
        ):
            removed.append(f"description @ {name}: {item['description']}")
            item["description"] = ""
        projects.append(item)
    data["projects"] = projects

    data["certifications"] = keep_sentences(data.get("certifications"), "certification")
    data["achievements"] = keep_sentences(data.get("achievements"), "achievement")

    return data, list(dict.fromkeys(removed))


# ============================================================
# Build the new profile.json
# ============================================================

def _cgpa(value):
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return float(match.group()) if match else None


def merge_profile(old, data):
    """
    Resume facts replace the old ones; everything a resume cannot know
    (target roles, preferences, strategy) is carried over untouched.
    """
    profile = dict(old)
    parsed = data.get("candidate") or {}

    candidate = dict(old.get("candidate") or {})
    if parsed.get("name"):
        candidate["full_name"] = parsed["name"]
        candidate.setdefault("name", parsed["name"].split()[0])
    for key in ("degree", "university", "duration", "location"):
        if parsed.get(key):
            candidate[key] = parsed[key]
    if _cgpa(parsed.get("cgpa")) is not None:
        candidate["cgpa"] = _cgpa(parsed["cgpa"])
    profile["candidate"] = candidate

    profile["skills"] = {
        "strong": data["skills_demonstrated"],
        "working": data["skills_listed_only"],
        "other": [],
    }

    profile["experience"] = [
        {
            "role": item.get("role", ""),
            "company": item.get("company", ""),
            "period": item.get("period", ""),
            "technologies": item.get("technologies", []),
            "highlights": item.get("highlights", []),
        }
        for item in data["experience"]
    ]

    projects = [
        {
            "name": item["name"],
            "type": item.get("tagline", ""),
            "description": item.get("description", ""),
            "technologies": item.get("technologies", []),
        }
        for item in data["projects"]
    ]

    # Projects you added to the profile yourself that were never on a
    # resume (marked "on_resume": false, e.g. a capstone in progress) are
    # kept, clearly labelled. Projects that came from the previous resume
    # and are gone from this one are dropped: the resume is the truth.
    resume_names = [_norm(p["name"]) for p in projects]
    kept_extra = []
    for project in old.get("projects") or []:
        if project.get("on_resume") is not False:
            continue
        key = _norm(project.get("name", ""))
        if key and not any(key in name or name in key for name in resume_names):
            projects.append(project)
            kept_extra.append(project.get("name", ""))
    profile["projects"] = projects

    profile["education"] = data.get("education") or []
    profile["certifications"] = data.get("certifications") or []
    profile["resume_updated_at"] = datetime.now().isoformat(timespec="seconds")

    return profile, kept_extra


# ============================================================
# Build the new resume_base.md
# ============================================================

DEFAULT_TAIL = """## Tailoring Rules

When generating application material:

1. Never invent experience, skills, projects, achievements, metrics,
   responsibilities, or technologies not present in this document.
2. Do not claim professional experience with a technology merely because
   it appears in the skills section.
3. Use exact project and experience names from this document.
4. Do not exaggerate proficiency.
5. If the job requires a technology not listed here, treat it as a skill gap.
6. If information is unknown, state that it is unknown.
"""


def preserved_tail(old_resume):
    """Keep the hand-written preferences / tailoring rules sections."""
    match = re.search(r"^## Application Preferences", old_resume, re.MULTILINE)
    if match:
        return old_resume[match.start():].strip() + "\n"
    match = re.search(r"^## Tailoring Rules", old_resume, re.MULTILINE)
    if match:
        return old_resume[match.start():].strip() + "\n"
    return DEFAULT_TAIL


def render_resume(data, profile, old_resume):
    candidate = data.get("candidate") or {}
    name = candidate.get("name") or (profile.get("candidate") or {}).get("full_name", "")
    out = [f"# {name} — Resume Base", "", "## Candidate", ""]

    for label, key in (
        ("Name", "name"), ("Location", "location"), ("Email", "email"),
        ("Phone", "phone"), ("Degree", "degree"), ("University", "university"),
        ("Duration", "duration"), ("CGPA", "cgpa"),
    ):
        if candidate.get(key):
            out.append(f"- {label}: {candidate[key]}")

    if data.get("summary"):
        out += ["", "---", "", "## Professional Summary", "", data["summary"]]

    roles = profile.get("target_roles") or {}
    if roles:
        out += ["", "---", "", "## Target Roles"]
        for heading, key in (("Primary", "primary"), ("Secondary", "secondary")):
            if roles.get(key):
                out += ["", f"### {heading}", ""] + [f"- {r}" for r in roles[key]]

    if data["skill_groups"]:
        out += ["", "---", "", "## Technical Skills"]
        for group in data["skill_groups"]:
            out += ["", f"### {group['group'] or 'Skills'}", ""]
            out += [f"- {item}" for item in group["items"]]

    if data["experience"]:
        out += ["", "---", "", "## Professional Experience"]
        for item in data["experience"]:
            out += ["", f"### {item.get('role', '')}", ""]
            if item.get("company"):
                out.append(f"**{item['company']}**")
            if item.get("period"):
                out.append(f"**{item['period']}**")
            out.append("")
            out += [f"- {h}" for h in item.get("highlights", [])]

    if data["projects"]:
        out += ["", "---", "", "## Projects"]
        for item in data["projects"]:
            out += ["", f"### {item['name']}", ""]
            if item.get("tagline"):
                out += [f"**{item['tagline']}**", ""]
            out += [f"- {h}" for h in item.get("highlights", [])]

    if data.get("education"):
        out += ["", "---", "", "## Education"]
        for item in data["education"]:
            out += ["", f"### {item.get('degree', '')}", ""]
            if item.get("institution"):
                out.append(f"**{item['institution']}**")
            if item.get("period"):
                out.append(f"**{item['period']}**")
            if item.get("score"):
                out.append(item["score"])

    if data.get("certifications"):
        out += ["", "---", "", "## Certifications", ""]
        out += [f"- {c}" for c in data["certifications"]]

    if data.get("achievements"):
        out += ["", "---", "", "## Achievements", ""]
        out += [f"- {a}" for a in data["achievements"]]

    out += ["", "---", "", preserved_tail(old_resume)]

    return "\n".join(out)


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", required=True, help="PDF, DOCX, MD or TXT.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing any file.",
    )
    args = parser.parse_args()

    print("""
===================================
     PROFILE UPDATE FROM RESUME
===================================
""")

    resume_path = Path(args.resume)

    if not resume_path.exists():
        print(f"ERROR: {resume_path} not found.")
        sys.exit(1)

    try:
        resume_text = extract_text(resume_path)
    except Exception as error:  # noqa: BLE001
        print(f"ERROR: could not read the resume: {error}")
        sys.exit(1)

    resume_text = resume_text.strip()

    if len(resume_text) < MIN_RESUME_CHARS:
        print(
            "ERROR: almost no text could be read from this file. If it is "
            "a scanned/image PDF, export a text-based PDF or use DOCX."
        )
        sys.exit(1)

    print(f"✓ Read {resume_path.name} ({len(resume_text)} characters)")
    print("Interpreting the resume...")

    try:
        data = interpret_resume(apply_assist.create_client(), resume_text)
    except Exception as error:  # noqa: BLE001
        print(f"ERROR: Gemini could not interpret the resume: {error}")
        sys.exit(1)

    data, removed = ground(data, resume_text)

    if not (data["experience"] or data["projects"] or data["skills_demonstrated"]):
        print(
            "ERROR: nothing usable was extracted, so the existing profile "
            "was left untouched."
        )
        sys.exit(1)

    old_profile = apply_assist.load_json(PROFILE_FILE, {})
    old_resume = apply_assist.load_text(RESUME_FILE, "")

    profile, kept_extra = merge_profile(old_profile, data)
    resume_md = render_resume(data, profile, old_resume)

    # ---------------- Report ----------------
    print(f"\nExperience entries : {len(data['experience'])}")
    print(f"Projects on resume : {len(data['projects'])}")
    print(f"Skills demonstrated: {len(data['skills_demonstrated'])}")
    print(f"Skills listed only : {len(data['skills_listed_only'])}")

    if kept_extra:
        print(
            "\nKept from your existing profile (not on this resume): "
            + ", ".join(kept_extra)
        )
        print("  Remove them from profile/profile.json if they no longer apply.")

    if removed:
        print(
            f"\n⚠ {len(removed)} item(s) were returned by the model but "
            "could not be found in the resume, so they were dropped:"
        )
        for item in removed:
            print(f"  - {item}")

    if args.dry_run:
        print("\n(dry run — no files were written)")
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = BACKUP_DIR / stamp
        backup.mkdir(parents=True, exist_ok=True)
        for path in (PROFILE_FILE, RESUME_FILE):
            if path.exists():
                shutil.copy2(path, backup / path.name)
        print(f"\nBacked up previous profile → {backup.relative_to(BASE_DIR)}")

        apply_assist.save_json(PROFILE_FILE, profile)
        RESUME_FILE.write_text(resume_md, encoding="utf-8")
        print("✓ profile/profile.json updated")
        print("✓ profile/resume_base.md updated")

    print("\n-----------------------------------")
    print("CAREER BRAIN (what jobs are now scored against)")
    print("-----------------------------------")
    print(build_career_brain(profile))

    if not args.dry_run:
        print(
            "Existing scores were made against the old profile. To re-score "
            "them:  python batch_analyzer.py --reanalyze"
        )


if __name__ == "__main__":
    main()