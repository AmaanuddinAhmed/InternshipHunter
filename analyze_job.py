import json
from pathlib import Path
from google import genai
from dotenv import load_dotenv
import os

from career_brain import load_career_brain

load_dotenv()

# Single place to change the Gemini model (or set GEMINI_MODEL in .env).
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# The Career Brain is derived from profile/profile.json (see career_brain.py),
# so a resume upload updates what every analysis is scored against.
CAREER_BRAIN = load_career_brain()

PROMPT = """
You are Amaan's Job Analyzer.

Analyze the supplied Job Description against the Career Brain.

Rules:
1. Never invent candidate skills, experience, salary, eligibility, PPO or company facts.
2. Identify hard eligibility blockers BEFORE scoring.
3. Explicit experience, degree, graduation-year, mandatory technology,
   and mandatory work-mode/location requirements can be blockers.
4. Good-to-have skills are NOT blockers.
5. Unknown stipend = UNKNOWN.
6. Incentive-only compensation is NOT guaranteed compensation.
7. PPO is highly important.
8. If PPO/conversion is explicitly mentioned, increase PPO score.
9. If candidate availability is unknown, do not invent it.
10. Recommend the most appropriate resume version.
11. Give concise interview topics.
12. Return ONLY JSON.


Scoring:
Give EVERY sub-score on the same 0-100 scale (100 = perfect on that
dimension). Do NOT pre-multiply by the weights below — the weighted
overall score is computed afterwards from your sub-scores.

Technical Fit 30%
Experience Fit 20%
Role Fit 15%
PPO 15%
Compensation 10%
Opportunity Quality 10%

Experience Fit must take the candidate's real work experience in the
Career Brain into account, not only the projects.

Recommendation:
90+ APPLY ASAP
80-89 APPLY
70-79 CONSIDER
60-69 STRETCH
Below 60 SKIP

If there is a genuine hard blocker, recommendation MUST be SKIP.

CAREER BRAIN:
""" + CAREER_BRAIN

schema = {
    "type": "OBJECT",
    "properties": {
        "company": {"type": "STRING"},
        "role": {"type": "STRING"},
        "job_url": {"type": "STRING"},
        "location": {"type": "STRING"},
        "work_mode": {"type": "STRING"},
        "job_type": {"type": "STRING"},
        "duration": {"type": "STRING"},

        "stipend": {
            "type": "OBJECT",
            "properties": {
                "status": {"type": "STRING"},
                "raw": {"type": "STRING"},
                "guaranteed_min_inr": {"type": "INTEGER"},
                "guaranteed_max_inr": {"type": "INTEGER"},
                "incentive_included": {"type": "BOOLEAN"}
            },
            "required": [
                "status",
                "raw",
                "guaranteed_min_inr",
                "guaranteed_max_inr",
                "incentive_included"
            ]
        },

        "eligibility": {
            "type": "OBJECT",
            "properties": {
                "status": {"type": "STRING"},
                "reasons": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"}
                }
            },
            "required": ["status", "reasons"]
        },

        "availability": {
            "type": "OBJECT",
            "properties": {
                "status": {"type": "STRING"},
                "reason": {"type": "STRING"}
            },
            "required": ["status", "reason"]
        },

        "ppo": {
            "type": "OBJECT",
            "properties": {
                "status": {"type": "STRING"},
                "evidence": {"type": "STRING"}
            },
            "required": ["status", "evidence"]
        },

        "required_skills": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },

        "preferred_skills": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },

        "demonstrated_matches": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },

        "skill_gaps": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },

        "hard_blockers": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },

        "red_flags": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },

        "scores": {
            "type": "OBJECT",
            "properties": {
                "technical_fit": {"type": "INTEGER"},
                "experience_fit": {"type": "INTEGER"},
                "role_fit": {"type": "INTEGER"},
                "ppo_score": {"type": "INTEGER"},
                "compensation_fit": {"type": "INTEGER"},
                "opportunity_quality": {"type": "INTEGER"},
                "overall_score": {"type": "INTEGER"}
            },
            "required": [
                "technical_fit",
                "experience_fit",
                "role_fit",
                "ppo_score",
                "compensation_fit",
                "opportunity_quality",
                "overall_score"
            ]
        },

        "recommendation": {"type": "STRING"},
        "recommended_resume": {"type": "STRING"},

        "interview_topics": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },

        "reasoning": {
            "type": "OBJECT",
            "properties": {
                "why_apply": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"}
                },
                "why_not": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"}
                }
            },
            "required": ["why_apply", "why_not"]
        }
    },

    "required": [
        "company",
        "role",
        "job_url",
        "location",
        "work_mode",
        "job_type",
        "duration",
        "stipend",
        "eligibility",
        "availability",
        "ppo",
        "required_skills",
        "preferred_skills",
        "demonstrated_matches",
        "skill_gaps",
        "hard_blockers",
        "red_flags",
        "scores",
        "recommendation",
        "recommended_resume",
        "interview_topics",
        "reasoning"
    ]
}

WEIGHTS = {
    "technical_fit": 0.30,
    "experience_fit": 0.20,
    "role_fit": 0.15,
    "ppo_score": 0.15,
    "compensation_fit": 0.10,
    "opportunity_quality": 0.10,
}

NO_BLOCKER_WORDS = {"", "none", "n/a", "na", "nil", "no", "no blockers", "none identified"}


def recommendation_for(score):
    if score >= 90:
        return "APPLY ASAP"
    if score >= 80:
        return "APPLY"
    if score >= 70:
        return "CONSIDER"
    if score >= 60:
        return "STRETCH"
    return "SKIP"


def finalize_analysis(result):
    """
    Make scoring deterministic after the model responds:

    - every sub-score is on 0-100 (a response that pre-multiplied by the
      weights, e.g. technical_fit 27 meaning 27/30, is rescaled);
    - overall_score is the weighted sum, computed here;
    - recommendation follows the score bands, and any real hard blocker
      forces SKIP.
    """
    scores = result.get("scores") or {}

    def num(key):
        try:
            return float(scores.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    raw = {key: num(key) for key in WEIGHTS}
    model_overall = num("overall_score")

    looks_pre_weighted = (
        model_overall > 0
        and all(raw[key] <= weight * 100 for key, weight in WEIGHTS.items())
        and abs(sum(raw.values()) - model_overall) <= 3
    )
    if looks_pre_weighted:
        raw = {key: raw[key] / WEIGHTS[key] for key in WEIGHTS}

    for key in WEIGHTS:
        scores[key] = int(round(max(0, min(100, raw[key]))))

    overall = int(round(sum(scores[key] * WEIGHTS[key] for key in WEIGHTS)))
    scores["overall_score"] = overall
    result["scores"] = scores

    blockers = [
        str(item).strip()
        for item in (result.get("hard_blockers") or [])
        if str(item).strip().lower().rstrip(".") not in NO_BLOCKER_WORDS
    ]
    result["hard_blockers"] = blockers
    result["recommendation"] = (
        "SKIP" if blockers else recommendation_for(overall)
    )

    return result


def main():

    job_file = Path("job.txt")

    if not job_file.exists():
        print("ERROR: job.txt not found.")
        return

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("ERROR: GEMINI_API_KEY is not set.")
        print('Run: $env:GEMINI_API_KEY="YOUR_KEY"')
        return

    jd = job_file.read_text(encoding="utf-8")

    client = genai.Client(api_key=api_key)


    response = client.models.generate_content(
        model=MODEL,
        contents=PROMPT + "\n\nJOB DESCRIPTION:\n" + jd,
        config={
            "response_mime_type": "application/json",
            "response_schema": schema
        }
    )

    result = finalize_analysis(json.loads(response.text))

    Path("analysis.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\nAnalysis complete!")
    print("Company:", result["company"])
    print("Role:", result["role"])
    print("Score:", result["scores"]["overall_score"])
    print("Recommendation:", result["recommendation"])
    print("\nSaved → analysis.json")


if __name__ == "__main__":
    main()