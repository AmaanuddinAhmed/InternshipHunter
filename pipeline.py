import json
import re


INPUT_FILE = "jobs_raw.json"
OUTPUT_FILE = "jobs_filtered.json"


# Roles we actively want
TARGET_TERMS = [
    "software engineer",
    "software developer",
    "software development",
    "sde",
    "full stack",
    "full-stack",
    "backend",
    "back-end",
    "node.js",
    "nodejs",
    "mern",
    "react",
    "java developer",
    "python developer",
    "ai engineer",
    "machine learning",
    "ml engineer",
    "devops",
    "cloud engineer",
]


# Terms that usually indicate the role is not suitable.
# Matched as whole words (see is_relevant) so e.g. "lead" doesn't reject a
# "Lead Generation Intern" posting, and "sr" doesn't match inside "user".
SENIOR_TERMS = [
    "senior",
    "sr",
    "lead",
    "principal",
    "manager",
    "architect",
    "director",
    "3+ years",
    "4+ years",
    "5+ years",
    "6+ years",
    "7+ years",
    "8+ years",
]


# Internship/apprenticeship/entry-level signals
ENTRY_TERMS = [
    "intern",
    "internship",
    "apprentice",
    "trainee",
    "fresher",
    "entry level",
    "entry-level",
    "graduate",
]


def clean_text(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def _contains_word(text, term):
    """
    Whole-word / whole-phrase containment. Prevents "lead" from matching
    "Lead Generation Intern" or "sr" from matching inside another word,
    while still allowing multi-word phrases like "3+ years" to match as-is.
    """
    if " " in term or "+" in term:
        return term in text
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def is_relevant(job):
    title = clean_text(job.get("title"))
    snippet = clean_text(job.get("snippet"))
    job_type = clean_text(job.get("type"))
    description = clean_text(job.get("description"))[:600]

    # Full text is used for positive signals (target role + entry level).
    combined = f"{title} {snippet} {job_type} {description}"

    # Senior detection stays on the title + job type only. Snippets and
    # JDs routinely mention "senior" or "lead" in passing (e.g. "reports
    # to a senior engineer", "lead generation") without the posting
    # itself being a senior role, so they're excluded from this check.
    senior_scope = f"{title} {job_type}"

    has_target_role = any(term in combined for term in TARGET_TERMS)
    has_entry_signal = any(term in combined for term in ENTRY_TERMS)

    # Obvious senior positions are removed before AI analysis.
    is_senior = any(_contains_word(senior_scope, term) for term in SENIOR_TERMS)

    if is_senior:
        return False

    if not has_target_role:
        return False

    if not has_entry_signal:
        return False

    return True


def main():

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    filtered = []

    for job in jobs:
        if is_relevant(job):
            filtered.append(job)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            filtered,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\n===================================")
    print("       JOB PRE-FILTER")
    print("===================================")
    print(f"Raw jobs:      {len(jobs)}")
    print(f"Relevant jobs: {len(filtered)}")
    print(f"Removed:       {len(jobs) - len(filtered)}")
    print(f"Saved → {OUTPUT_FILE}")
    print("===================================\n")


if __name__ == "__main__":
    main()