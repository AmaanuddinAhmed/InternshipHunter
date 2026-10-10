# InternshipHunter

A personal internship pipeline: discover jobs, filter them, score each one
against your profile with Gemini, build an application kit for the good
ones, and track everything in an Excel CRM. On top of that, a **Morning
brief** page puts the day's work on one screen: follow-ups due, new roles,
companies to message, and who you are waiting on. Nothing is ever submitted
or sent for you — every application and message goes out by hand.

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

Start each morning at http://127.0.0.1:5000/brief.

| Step | Script              | What it does                                                                |
| ---- | ------------------- | --------------------------------------------------------------------------- |
| 1    | `discover.py`       | Pulls jobs from every configured source into `jobs_raw.json`, de-duplicated |
| 2    | `pipeline.py`       | Keyword pre-filter into `jobs_filtered.json`                                |
| 3    | `batch_analyzer.py` | Gemini scores each new job into `analyses.json`                             |
| 4    | `apply_assist.py`   | Builds kits for APPLY / APPLY ASAP jobs in `applications/`                  |
| 5    | `crm_importer.py`   | Writes results into the `Jobs` sheet                                        |
| 6    | `dashboard.py`      | Rebuilds the Morning Dashboard sheet                                        |
| 7    | `leads.py`          | Refreshes company leads (YC India + funding news) into `leads.json`         |

## Where jobs come from

| Source       | What it is                                                        | Needs            |
| ------------ | ----------------------------------------------------------------- | ---------------- |
| `watchlist`  | Careers pages of companies you choose (Greenhouse / Lever / Ashby) | `watchlist.json` |
| `jooble`     | Job-board aggregator                                              | `JOOBLE_API_KEY` |
| `adzuna`     | Job-board aggregator                                              | Adzuna keys      |
| `internshala`| Software / web development internships, Bangalore + remote         | —                |
| `unstop`     | Open internships from Unstop's public listing API                  | —                |
| `hn_whoishiring` | Hacker News "Who is hiring?" threads                           | —                |

Wellfound, LinkedIn and Y Combinator's job pages are not scraped: the first
two block automated readers, and YC's public pages list almost no
entry-level roles in India. Use them by hand and bring anything good in
with _Add a job I found myself_. YC companies show up as **leads** instead.

## Watchlist

    python watchlist.py                       # list
    python watchlist.py add <careers-url>     # Greenhouse / Lever / Ashby link
    python watchlist.py probe "Postman" "Groww"   # find boards by name
    python watchlist.py probe --leads         # try every company in leads.json
    python watchlist.py check                 # test every entry

`probe` guesses the board address from the company name, so open the link
it prints once to confirm it is the right company. Companies on other
systems (Workday, Keka, Darwinbox, their own page) cannot be watched.

## Morning brief, leads and outreach

- **Leads** (`leads.json`): YC companies based in India that are hiring,
  plus Indian startups in the last two weeks of funding news.
- **Outreach** (`outreach.json`): log each message you send; it comes back
  as a follow-up 5 days later, and drops off 10 days after the follow-up.
- **Drafts** are built only from `profile/profile.json`. Anything missing is
  left as a `[bracketed]` blank. To fill the blanks once, add to
  `profile.json`:

      "outreach": {
        "availability": "full-time from January 2027",
        "proof_line": "one sentence on the best thing you have shipped",
        "portfolio": "https://your-portfolio"
      }

      python brief.py       # the brief in the terminal
      python outreach.py    # open outreach and what is due

## Running it every morning (Windows)

    schtasks /Create /SC DAILY /ST 06:30 /TN "InternshipHunter" /TR "\"C:\path\to\InternshipHunter\run_daily.bat\""

The PC has to be on (or set the task to wake it in Task Scheduler →
Conditions). Output goes to `daily.log`.

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
  `python add_job.py --url <link> --jd-file jd.txt`

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
