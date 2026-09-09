import json
from pathlib import Path
from google import genai
from dotenv import load_dotenv
import os

load_dotenv()

CAREER_BRAIN = """
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
Technical Fit 30%
Experience Fit 20%
Role Fit 15%
PPO 15%
Compensation 10%
Opportunity Quality 10%

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
        model="gemini-3.5-flash-lite",
        contents=PROMPT + "\n\nJOB DESCRIPTION:\n" + jd,
        config={
            "response_mime_type": "application/json",
            "response_schema": schema
        }
    )

    result = json.loads(response.text)

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