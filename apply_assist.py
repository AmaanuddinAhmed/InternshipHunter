import json
import re
import time
from pathlib import Path

from google import genai

import analyze_job


BASE_DIR = Path(__file__).resolve().parent

FILTERED_FILE = BASE_DIR / "jobs_filtered.json"
ANALYSES_FILE = BASE_DIR / "analyses.json"

PROFILE_DIR = BASE_DIR / "profile"
PROFILE_FILE = PROFILE_DIR / "profile.json"
RESUME_FILE = PROFILE_DIR / "resume_base.md"

APPLICATIONS_DIR = BASE_DIR / "applications"


# ============================================================
# Helpers
# ============================================================

def load_json(path, default):
    """Load JSON safely."""
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"  Warning: could not read {path.name}: {error}")
        return default


def save_json(path, data):
    """Save JSON using UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def load_text(path, default=""):
    """Load UTF-8 text safely."""
    if not path.exists():
        return default

    try:
        return path.read_text(encoding="utf-8")
    except Exception as error:
        print(f"  Warning: could not read {path.name}: {error}")
        return default


def clean_filename(value):
    """
    Convert an arbitrary value into a Windows-safe folder/file name.
    """
    value = str(value or "").strip()

    value = re.sub(
        r'[<>:"/\\|?*]',
        "_",
        value
    )

    value = re.sub(
        r"\s+",
        "_",
        value
    )

    value = value.strip(" ._")

    return value[:100] or "unknown_job"


def get_job_key(job):
    """
    URL is the primary identity key.
    Fall back to job_id if URL is unavailable.
    """
    url = str(job.get("url", "")).strip()

    if url:
        return url

    return str(job.get("job_id", "")).strip()


def get_analysis_job(analysis):
    """
    Return the original job embedded inside an analysis.
    """
    if not isinstance(analysis, dict):
        return {}

    job = analysis.get("_job")

    if isinstance(job, dict):
        return job

    return {}


def get_analysis_key(analysis):
    """
    Resolve the identity of an analyzed job.
    """
    job = get_analysis_job(analysis)

    url = str(
        analysis.get("job_url")
        or job.get("url")
        or ""
    ).strip()

    if url:
        return url

    return str(
        job.get("job_id")
        or analysis.get("job_id")
        or ""
    ).strip()


def get_recommendation(analysis):
    """
    Support the recommendation field used by the analyzer.
    """
    value = (
        analysis.get("recommendation")
        or analysis.get("decision")
        or ""
    )

    return str(value).strip().upper()


def get_application_folder(job):
    """
    Create a stable application folder based primarily on job_id.
    """
    job_id = clean_filename(
        job.get("job_id")
        or get_job_key(job)
    )

    return APPLICATIONS_DIR / job_id


def extract_retry_seconds(error):
    """
    Extract Gemini's suggested retry delay where available.
    """
    text = str(error)

    match = re.search(
        r"retry in\s+([\d.]+)s",
        text,
        re.IGNORECASE
    )

    if match:
        return max(5, int(float(match.group(1))) + 2)

    return 60


# ============================================================
# Prompt
# ============================================================

APPLY_ASSIST_PROMPT = """
You are an AI application assistant helping a candidate apply for
software engineering internships.

Your job is to create a truthful, highly tailored, application-ready kit
for ONE specific job.

The candidate will personally review everything before submitting it.

============================================================
SOURCE OF TRUTH
============================================================

Candidate information may ONLY come from:

1. CANDIDATE PROFILE
2. CANDIDATE RESUME

Job information may ONLY come from:

3. JOB
4. JOB DESCRIPTION

Never invent facts.

Never assume facts that are not supported by the supplied information.

============================================================
NON-NEGOTIABLE TRUTHFULNESS RULES
============================================================

1. Never invent experience, employment, projects, technologies,
   achievements, metrics, responsibilities, certifications, education,
   dates, companies, or job duties.

2. Do not claim professional experience with a technology merely because
   it appears in the candidate's skills.

3. Do not claim the candidate has used a technology in production unless
   the resume explicitly supports that claim.

4. If a job requires a technology that is not clearly demonstrated,
   identify it as a skill gap.

5. Never fabricate company facts, products, culture, mission, funding,
   customers, or business details.

6. For "why this company", only use company-specific information actually
   present in the job description.

7. Do not use generic praise such as:
   "exciting company",
   "leading organization",
   "innovative company",
   "great opportunity",
   unless the supplied job description itself provides evidence
   supporting that description.

8. Never tell the candidate to lie, exaggerate, or hide a material
   eligibility problem.

9. All generated material must be defensible in an interview.

============================================================
JOB ANALYSIS
============================================================

Before generating the application kit, identify internally:

- Most important technical requirements
- Most relevant responsibilities
- Required experience level
- Location/work mode
- Internship duration
- Stipend/salary if provided
- Important eligibility requirements
- Strongest candidate-to-job matches
- Important candidate skill gaps

Use this analysis to tailor the output.

============================================================
TAILORED RESUME BULLETS
============================================================

Generate 3–6 bullets.

Select the strongest existing experience/project bullets for THIS job.

Rewrite them only to improve relevance, clarity, and emphasis.

Prioritize:

- directly matching technologies
- directly matching responsibilities
- production experience
- relevant projects
- measurable results only when explicitly present in the resume

Do NOT create fake metrics.

Do NOT simply copy the entire job description.

Do NOT include irrelevant projects just to increase the number of bullets.

============================================================
COVER LETTER
============================================================

Generate approximately 150–220 words.

Structure:

1. Specific opening for the role.
2. Strongest relevant professional experience.
3. One or two highly relevant projects/technical strengths.
4. Evidence-based connection to the job.
5. Concise closing.

For company-specific statements, use ONLY facts contained in the
job description.

Avoid generic filler.

Avoid phrases such as:

"I am extremely passionate..."
"I have always admired..."
"I believe I would be a perfect fit..."

unless they are genuinely necessary.

The letter should sound like a technically capable student applying
professionally, not like generic AI-generated text.

============================================================
SCREENING ANSWERS
============================================================

Generate concise answers that can be pasted directly into application
forms.

Each answer must answer the exact question represented by its heading.

--------------------------------
why_this_company
--------------------------------

Use specific information from the job description.

If the JD does not contain meaningful company information, give a
role-focused answer instead of inventing company-specific facts.

--------------------------------
why_this_role
--------------------------------

Connect the actual responsibilities and technologies in the JD to the
candidate's demonstrated experience.

--------------------------------
why_you
--------------------------------

Use the candidate's strongest verified experience and projects.

Avoid generic claims such as "hardworking" or "passionate" unless supported
by concrete evidence.

--------------------------------
availability
--------------------------------

Only state availability information explicitly provided by the candidate.

If exact availability is unknown, say:

"Availability should be confirmed with the candidate."

Do NOT invent dates.

--------------------------------
expected_stipend
--------------------------------

If the JD provides a stipend range, respect that range.

Use the candidate's preferred minimum only when appropriate.

Do NOT automatically request the maximum available amount.

If the application asks for a single number and the JD gives a range,
recommend a reasonable value within the posted range while considering
the candidate's stated preference.

If no stipend is provided, say:

"Open to discussion based on the company's internship compensation."

--------------------------------
relocation
--------------------------------

Answer relocation questions directly.

These are separate concepts:

- Current location
- Remote-work preference
- Willingness to relocate

Never infer willingness to relocate merely because the candidate is
open to remote work.

If the candidate's resume/profile does not explicitly establish
relocation willingness, return exactly:

"Relocation preference should be confirmed with the candidate."

Do not use the job's remote status as an answer to a relocation question.

--------------------------------
relevant_technology_experience
--------------------------------

Mention ONLY technologies actually demonstrated in the candidate profile
or resume.

Prioritize technologies relevant to the job.

============================================================
SKILLS TO HIGHLIGHT
============================================================

Return the candidate's strongest skills that directly match the job.

Do not list every skill from the resume.

============================================================
SKILL GAPS
============================================================

List important requirements from the job that are not clearly demonstrated
in the candidate profile/resume.

Do not treat a skill as a gap if the candidate clearly demonstrates it.

============================================================
APPLICATION STRATEGY
============================================================

Give 3–5 practical instructions for applying to this specific job.

Examples:

- Which experience to emphasize
- Which project to mention
- Which skill gap to prepare for
- Whether the role's location/work mode needs attention
- What screening question deserves special care

Do not give generic advice such as "proofread your resume."

============================================================
CONFIDENCE
============================================================

Return:

HIGH
- JD is detailed and candidate alignment is clear.

MEDIUM
- Some useful information exists but important details are missing.

LOW
- JD is thin or candidate alignment cannot be evaluated confidently.

============================================================
OUTPUT
============================================================

Return ONLY valid JSON matching the supplied schema.

No markdown fences.

No commentary outside the JSON.

Do not include unsupported claims.
"""


# ============================================================
# JSON Schema
# ============================================================

APPLICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "tailored_resume_bullets": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "cover_letter": {
            "type": "string"
        },
        "screening_answers": {
            "type": "object",
            "properties": {
                "why_this_company": {
                    "type": "string"
                },
                "why_this_role": {
                    "type": "string"
                },
                "why_you": {
                    "type": "string"
                },
                "availability": {
                    "type": "string"
                },
                "expected_stipend": {
                    "type": "string"
                },
                "relocation": {
                    "type": "string"
                },
                "relevant_technology_experience": {
                    "type": "string"
                }
            },
            "required": [
                "why_this_company",
                "why_this_role",
                "why_you",
                "availability",
                "expected_stipend",
                "relocation",
                "relevant_technology_experience"
            ]
        },
        "skills_to_highlight": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "skill_gaps": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "application_strategy": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "confidence": {
            "type": "string",
            "enum": [
                "HIGH",
                "MEDIUM",
                "LOW"
            ]
        }
    },
    "required": [
        "tailored_resume_bullets",
        "cover_letter",
        "screening_answers",
        "skills_to_highlight",
        "skill_gaps",
        "application_strategy",
        "confidence"
    ]
}


# ============================================================
# Gemini
# ============================================================

def create_client():
    """
    Reuse the API key configuration from analyze_job.py.
    """
    api_key = getattr(analyze_job, "API_KEY", None)

    if api_key:
        return genai.Client(api_key=api_key)

    return genai.Client()


def build_job_context(job):
    """
    Prefer the full description and fall back to snippet.
    """
    description = (
        str(job.get("description") or "").strip()
        or str(job.get("snippet") or "").strip()
    )

    return (
        f"JOB\n"
        f"Company: {job.get('company', '')}\n"
        f"Role: {job.get('title', '')}\n"
        f"Location: {job.get('location', '')}\n"
        f"Remote: {job.get('remote', '')}\n"
        f"Job Type: {job.get('type', '')}\n"
        f"Salary/Stipend: {job.get('salary', '')}\n"
        f"Source: {job.get('source', '')}\n"
        f"URL: {job.get('url', '')}\n"
        f"Posted: {job.get('posted', '')}\n\n"
        f"JOB DESCRIPTION:\n"
        f"{description}"
    )


def build_candidate_context(profile, resume):
    """
    Combine structured profile data with the real resume base.
    """
    return (
        "CANDIDATE PROFILE\n\n"
        + json.dumps(
            profile,
            indent=2,
            ensure_ascii=False
        )
        + "\n\n"
        "CANDIDATE RESUME\n\n"
        + resume
    )


def generate_application_kit(
    client,
    job,
    profile,
    resume
):
    """
    Generate one application kit using Gemini.
    """

    job_context = build_job_context(job)

    candidate_context = build_candidate_context(
        profile,
        resume
    )

    prompt = (
        APPLY_ASSIST_PROMPT
        + "\n\n"
        + candidate_context
        + "\n\n"
        + job_context
    )

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": APPLICATION_SCHEMA
        }
    )

    return json.loads(response.text)


# ============================================================
# File generation
# ============================================================

def clean_generated_text(text):
    """
    Clean minor formatting artifacts from model output without
    changing the substantive content.
    """
    if not isinstance(text, str):
        return text

    # Common model formatting artifacts.
    replacements = {
        "â‚¹": "₹",
        "â€”": "—",
        "â€“": "–",
        "realcustomer": "real customer",
        "atSunflower": "at Sunflower",
        "theplatform": "the platform",
        "JWTauthentication": "JWT authentication",
        "Joi-based": "Joi-based",
        "SQLServer": "SQL Server",
        "cloudplatforms": "cloud platforms",
        "contributingto": "contributing to",
        "aligningwell": "aligning well"
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Fix common missing spaces between lowercase/uppercase word boundaries.
    text = re.sub(
        r"([a-z])([A-Z][a-z]+)",
        r"\1 \2",
        text
    )

    # Fix missing spaces after punctuation where the next word is obvious.
    text = re.sub(
        r",([A-Za-z])",
        r", \1",
        text
    )

    text = re.sub(
        r"\.([A-Za-z])",
        r". \1",
        text
    )

    # Collapse accidental multiple spaces.
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    return text.strip()

def write_markdown_files(folder, kit):
    """
    Generate human-readable application files.
    """

    resume_bullets = [
        clean_generated_text(bullet)
        for bullet in kit.get(
            "tailored_resume_bullets",
            []
        )
    ]

    cover_letter = clean_generated_text(
        kit.get(
            "cover_letter",
            ""
        )
    )


    screening = kit.get(
        "screening_answers",
        {}
    )

    skills = kit.get(
        "skills_to_highlight",
        []
    )

    gaps = kit.get(
        "skill_gaps",
        []
    )

    strategy = kit.get(
        "application_strategy",
        []
    )

    resume_text = "# Tailored Resume Bullets\n\n"

    for bullet in resume_bullets:
        resume_text += f"- {bullet}\n"

    cover_text = (
        "# Cover Letter\n\n"
        + cover_letter.strip()
        + "\n"
    )

    screening_text = "# Screening Answers\n\n"

    screening_labels = {
        "why_this_company": "Why this company?",
        "why_this_role": "Why this role?",
        "why_you": "Why you?",
        "availability": "Availability",
        "expected_stipend": "Expected stipend",
        "relocation": "Relocation",
        "relevant_technology_experience": (
            "Relevant technology experience"
        )
    }

    for key, label in screening_labels.items():
        screening_text += (
            f"## {label}\n\n"
            f"{clean_generated_text(screening.get(key, ''))}\n\n"
        )

    strategy_text = "# Application Strategy\n\n"

    for item in strategy:
        strategy_text += f"- {item}\n"

    strategy_text += "\n# Skills to Highlight\n\n"

    for skill in skills:
        strategy_text += f"- {skill}\n"

    strategy_text += "\n# Skill Gaps\n\n"

    if gaps:
        for gap in gaps:
            strategy_text += f"- {gap}\n"
    else:
        strategy_text += "- None clearly identified.\n"

    (folder / "resume_bullets.md").write_text(
        resume_text,
        encoding="utf-8"
    )

    (folder / "cover_letter.md").write_text(
        cover_text,
        encoding="utf-8"
    )

    (folder / "screening_answers.md").write_text(
        screening_text,
        encoding="utf-8"
    )

    (folder / "application_strategy.md").write_text(
        strategy_text,
        encoding="utf-8"
    )


def save_application_kit(
    folder,
    job,
    kit
):
    """
    Save structured kit + metadata.
    """

    output = {
        "job": {
            "job_id": job.get("job_id"),
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "remote": job.get("remote"),
            "salary": job.get("salary"),
            "source": job.get("source"),
            "url": job.get("url")
        },
        "generated_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime()
        ),
        "status": "READY_FOR_REVIEW",
        "kit": kit
    }

    save_json(
        folder / "application_kit.json",
        output
    )

    write_markdown_files(
        folder,
        kit
    )


# ============================================================
# Main
# ============================================================

def main():

    print("""
===========================================
       AMAAN INTERNSHIP APPLY-ASSIST
===========================================
""")

    # --------------------------------------------------------
    # Load candidate profile
    # --------------------------------------------------------

    profile = load_json(
        PROFILE_FILE,
        {}
    )

    resume = load_text(
        RESUME_FILE,
        ""
    )

    if not profile:
        print("ERROR: profile/profile.json is missing or empty.")
        return

    if not resume.strip():
        print("ERROR: profile/resume_base.md is missing or empty.")
        return

    print("✓ Candidate profile loaded")
    print("✓ Resume base loaded")

    # --------------------------------------------------------
    # Load jobs + analyses
    # --------------------------------------------------------

    jobs = load_json(
        FILTERED_FILE,
        []
    )

    analyses = load_json(
        ANALYSES_FILE,
        []
    )

    if not isinstance(jobs, list):
        jobs = []

    if not isinstance(analyses, list):
        analyses = []

    print(f"Filtered jobs : {len(jobs)}")
    print(f"Analyses      : {len(analyses)}")

    # --------------------------------------------------------
    # Index jobs by identity
    # --------------------------------------------------------

    jobs_by_key = {}

    for job in jobs:
        if not isinstance(job, dict):
            continue

        key = get_job_key(job)

        if key:
            jobs_by_key[key] = job

    # --------------------------------------------------------
    # Select APPLY / APPLY ASAP jobs
    # --------------------------------------------------------

    candidates = []

    for analysis in analyses:

        if not isinstance(analysis, dict):
            continue

        recommendation = get_recommendation(
            analysis
        )

        if recommendation not in {
            "APPLY",
            "APPLY ASAP"
        }:
            continue

        key = get_analysis_key(
            analysis
        )

        job = jobs_by_key.get(key)

        if not job:
            job = get_analysis_job(
                analysis
            )

        if not job:
            continue

        candidates.append(
            (
                job,
                analysis
            )
        )

    print(
        f"Apply candidates: {len(candidates)}"
    )

    if not candidates:
        print(
            "\nNo APPLY / APPLY ASAP jobs "
            "require application kits."
        )
        print("===========================================")
        return

    # --------------------------------------------------------
    # Gemini
    # --------------------------------------------------------

    client = create_client()

    generated = 0
    skipped = 0
    failed = 0

    # --------------------------------------------------------
    # Generate kits
    # --------------------------------------------------------

    for index, (job, analysis) in enumerate(
        candidates,
        start=1
    ):

        folder = get_application_folder(
            job
        )

        kit_file = (
            folder
            / "application_kit.json"
        )

        company = job.get(
            "company",
            "Unknown"
        )

        title = job.get(
            "title",
            "Unknown"
        )

        print(
            f"\n[{index}/{len(candidates)}] "
            f"{company} — {title}"
        )

        # Do not regenerate existing kits.
        if kit_file.exists():

            print(
                "    ↳ application kit already exists — skipping"
            )

            skipped += 1

            continue

        try:

            kit = generate_application_kit(
                client,
                job,
                profile,
                resume
            )

            save_application_kit(
                folder,
                job,
                kit
            )

            generated += 1

            print(
                "    ✓ application kit generated"
            )

            print(
                f"    → {folder.relative_to(BASE_DIR)}"
            )

        except Exception as error:

            error_text = str(error)

            # ------------------------------------------------
            # Rate-limit handling
            # ------------------------------------------------

            if (
                "429" in error_text
                or "RESOURCE_EXHAUSTED"
                in error_text
                or "quota"
                in error_text.lower()
            ):

                wait_seconds = (
                    extract_retry_seconds(
                        error
                    )
                )

                print(
                    f"    ⚠ Gemini rate limit."
                )

                print(
                    f"    Waiting {wait_seconds}s..."
                )

                time.sleep(
                    wait_seconds
                )

                # Retry once.
                try:

                    kit = generate_application_kit(
                        client,
                        job,
                        profile,
                        resume
                    )

                    save_application_kit(
                        folder,
                        job,
                        kit
                    )

                    generated += 1

                    print(
                        "    ✓ application kit generated after retry"
                    )

                except Exception as retry_error:

                    failed += 1

                    print(
                        f"    ✗ retry failed: {retry_error}"
                    )

            else:

                failed += 1

                print(
                    f"    ✗ ERROR: {error}"
                )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print("""
===========================================
        APPLY-ASSIST COMPLETE
===========================================
""")

    print(
        f"Generated : {generated}"
    )

    print(
        f"Skipped   : {skipped}"
    )

    print(
        f"Failed    : {failed}"
    )

    print(
        f"Output    : {APPLICATIONS_DIR}"
    )

    print("""
Nothing was submitted automatically.
All generated material is for your review.
===========================================
""")


if __name__ == "__main__":
    main()
