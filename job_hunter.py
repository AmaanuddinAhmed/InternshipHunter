import requests
from datetime import datetime
import json
from dotenv import load_dotenv
import os

load_dotenv()

JOOBLE_API_KEY = os.getenv("JOOBLE_API_KEY")

if not JOOBLE_API_KEY:
    raise RuntimeError(
        "JOOBLE_API_KEY not found. Check your .env file."
    )


API_URL = f"https://in.jooble.org/api/{JOOBLE_API_KEY}"


SEARCH_QUERIES = [
    "software engineer intern",
    "software development intern",
    "full stack developer intern",
    "backend developer intern",
    "SDE intern",
    "Node.js intern",
    "MERN intern",
    "Java developer intern",
    "Python developer intern",
    "AI engineer intern",
]


def search_jobs(keyword, location="Bangalore"):
    payload = {
        "keywords": keyword,
        "location": location,
        "page": 1
    }

    response = requests.post(
        API_URL,
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


def normalize_job(job, query):
    return {
        "job_id": job.get("id"),
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "salary": job.get("salary"),
        "type": job.get("type"),
        "source": job.get("source"),
        "url": job.get("link"),
        "updated": job.get("updated"),
        "snippet": job.get("snippet"),
        "search_query": query,
        "found_at": datetime.now().isoformat()
    }


def main():

    all_jobs = []
    seen_ids = set()

    print("\n===================================")
    print("   AMAAN INTERNSHIP JOB HUNTER")
    print("===================================\n")

    for query in SEARCH_QUERIES:

        print(f"Searching: {query}")

        try:
            data = search_jobs(query)

            jobs = data.get("jobs", [])

            for job in jobs:

                job_id = job.get("id")

                if job_id and job_id in seen_ids:
                    continue

                if job_id:
                    seen_ids.add(job_id)

                all_jobs.append(
                    normalize_job(job, query)
                )

            print(f"  Found: {len(jobs)}")

        except Exception as e:
            print(f"  ERROR: {e}")

    output_file = "jobs_raw.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            all_jobs,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\n===================================")
    print(f"Total unique jobs: {len(all_jobs)}")
    print(f"Saved → {output_file}")
    print("===================================\n")


if __name__ == "__main__":
    main()