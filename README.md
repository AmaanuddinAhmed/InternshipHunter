# InternshipHunter

A personal internship pipeline: discover jobs, filter them, score each one
against your profile with Gemini, build an application kit for the good
ones, and track everything in an Excel CRM. Nothing is ever submitted for
you — every application is reviewed and sent by hand.

## Setup

    pip install -r requirements.txt

Create a `.env` file in the project root:

    GEMINI_API_KEY=...          # required
    JOOBLE_API_KEY=...          # optional source
    ADZUNA_APP_ID=...           # optional source
    ADZUNA_APP_KEY=...
    FIRECRAWL_API_KEY=...       # optional: full job descriptions (see below)

## Running it

    python webapp/app.py        # web UI at http://127.0.0.1:5000
    python daily.py             # or the whole pipeline from the terminal

| Step | Script              | What it does                                                                |
| ---- | ------------------- | --------------------------------------------------------------------------- |
| 1    | `discover.py`       | Pulls jobs from every configured source into `jobs_raw.json`, de-duplicated |
| 2    | `pipeline.py`       | Keyword pre-filter into `jobs_filtered.json`                                |
| 3    | `batch_analyzer.py` | Gemini scores each new job into `analyses.json`                             |
| 4    | `apply_assist.py`   | Builds kits for APPLY / APPLY ASAP jobs in `applications/`                  |
| 5    | `crm_importer.py`   | Writes results into the `Jobs` sheet                                        |
| 6    | `dashboard.py`      | Rebuilds the Morning Dashboard sheet                                        |

## Your profile

`profile/profile.json` and `profile/resume_base.md` are the only sources of
candidate facts. The Career Brain the analyzer scores against is derived
from `profile.json` (`python career_brain.py` prints it).

To update from a new resume, use **My profile & resume** in the web UI, or:

    python setup_profile.py --resume resume.pdf            # PDF, DOCX, MD, TXT
    python setup_profile.py --resume resume.pdf --dry-run  # preview only

Anything the model returns that is not found in the resume text is dropped
and reported. Target roles, stipend and location preferences are never
changed by a resume. The previous profile is saved in `profile/backups/`.
Projects you want considered that are not on your resume go in
`profile.json` with `"on_resume": false`.

After a profile change, re-score existing jobs with:

    python batch_analyzer.py --reanalyze

## Kits on demand

- **Any job:** open it in the web UI and press _Generate application kit_
  (or _Regenerate kit_). Terminal: `python apply_assist.py --url <job url> [--force]`
- **A job you found yourself:** _Add a job I found myself_ in the web UI —
  paste the description or just the link. Terminal:
  `python add_job.py --url <link> --jd-file job.txt`

## Firecrawl (optional)

Job APIs return only a 300–500 character snippet. With `FIRECRAWL_API_KEY`
set, the full posting is fetched:

- when a job scored 60+ on a thin snippet — it is re-scored on the full text
  (at most `FIRECRAWL_MAX_PER_RUN` per run, default 40);
- when a kit is generated from a thin description;
- when you add a job by URL without pasting its description.

Without the key everything still works on the snippets.

## Starting clean

    python reset_workspace.py

Clears discovered jobs, analyses and kits; keeps your profile.
