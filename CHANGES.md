# InternshipHunter update — what changed and where

Unzip `internshiphunter-update.zip` over the project root. It contains only
new files and four full-file replacements. Then make the edits in section 2
by hand and delete the files in section 3.

## 1. In the zip

New files:

| File | What it does |
| --- | --- |
| `sources/ats.py` | Watchlist source: reads Greenhouse / Lever / Ashby careers feeds |
| `watchlist.json` | Companies to watch (starts with CRED and Razorpay) |
| `watchlist.py` | `add` / `probe` / `check` commands for the watchlist |
| `leads.py` | Company leads: YC India (hiring) + funding news |
| `outreach.py` | Outreach log, follow-up dates, message drafts |
| `brief.py` | Builds the morning brief (also prints it in the terminal) |
| `webapp/brief_routes.py` | Web routes for the brief page |
| `webapp/templates/brief.html`, `webapp/static/brief.js`, `webapp/static/brief.css` | The brief page |
| `run_daily.bat` | For Windows Task Scheduler |

Replaced whole (overwrite yours):

- `sources/__init__.py` — registry now lists watchlist, jooble, adzuna, internshala, unstop, hn_whoishiring
- `sources/unstop.py` — now reads Unstop's public listing API
- `sources/internshala.py` — reads the software / web category pages and fills in company, location, stipend
- `README.md`

## 2. Edits to make by hand

### `webapp/app.py` — two additions

After these two lines:

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # resume uploads: 5 MB

add:

    # Morning brief page + its API (leads, outreach tracker, watchlist).
    from brief_routes import brief_bp  # noqa: E402

    app.register_blueprint(brief_bp)

In the `STEPS` list, after the `"dashboard"` entry, add:

    {
        "id": "leads",
        "label": "7. Company Leads",
        "script": "leads.py",
        "args": [],
    },

### `webapp/templates/base.html`

Inside `<nav>`, above the Dashboard link:

    <a href="/brief">Morning brief</a>

### `daily.py`

Just before the final `print("""` … `PIPELINE COMPLETE` block:

    # 7. Refresh company leads for the morning brief
    run_step(
        "7/7  COMPANY LEADS",
        "leads.py"
    )

Optional: rename the labels `1/6` … `6/6` to `1/7` … `6/7`.

### `pipeline.py`

In `TARGET_TERMS`, after `"reactjs",` add:

    "frontend",
    "front-end",
    "web developer",
    "web development",

Without this, Internshala's "Web Development" internships are filtered out
before scoring.

### `sources/config.py`

Delete `INDIA_METROS` and `ENTRY_TERMS`. Nothing uses them any more.

### `.gitignore`

Add:

    leads.json
    outreach.json
    daily.log

### `profile/profile.json` (optional)

Fills the blanks in message drafts. Add a top-level block in your own words:

    "outreach": {
      "availability": "full-time from January 2027",
      "proof_line": "one sentence on the best thing you have shipped",
      "portfolio": "https://your-portfolio"
    }

A resume upload keeps this block.

## 3. Files to delete

| File | Why |
| --- | --- |
| `sources/yc.py` | YC's public job pages list almost no entry-level India roles. YC is now a leads feed |
| `sources/wellfound.py` | Wellfound blocks automated readers. Results were "Software Engineer" rows with no location |
| `sources/themuse.py`, `sources/arbeitnow.py`, `sources/remoteok.py`, `sources/remotive.py`, `sources/jobicy.py` | Results were almost all on-site roles abroad or non-engineering, and each still cost an AI scoring call |
| `IMPORTER_README.md` | Covered by `README.md` |
| `job.txt` | A sample job description. `add_job.py --jd-file` takes any file |
| `Amaan_Internship_Ecosystem_v2_backup_before_reset.xlsx`, `jobs_raw.json` | Listed in `.gitignore` but committed. Run `git rm --cached <file>` on both, and delete the backup if you don't need it |

## 4. First run

    python watchlist.py check
    python watchlist.py probe "Company A" "Company B"
    python leads.py
    python watchlist.py probe --leads
    python daily.py
    python webapp/app.py

Then open http://127.0.0.1:5000/brief.
