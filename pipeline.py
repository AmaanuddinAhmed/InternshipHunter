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


# Terms that usually indicate the role is not suitable
SENIOR_TERMS = [
    "senior",
    "sr.",
    "sr ",
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


def is_relevant(job):
    title = clean_text(job.get("title"))
    snippet = clean_text(job.get("snippet"))
    job_type = clean_text(job.get("type"))

    combined = f"{title} {snippet} {job_type}"

    has_target_role = any(term in combined for term in TARGET_TERMS)
    has_entry_signal = any(term in combined for term in ENTRY_TERMS)

    # Obvious senior positions are removed before AI analysis.
    is_senior = any(term in combined for term in SENIOR_TERMS)

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