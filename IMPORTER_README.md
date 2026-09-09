# CRM Importer

Save the AI Job Analyzer's JSON response as `analysis.json`, then run:

`python crm_importer.py --analysis analysis.json --crm Amaan_Internship_Ecosystem_v2.xlsx`

The result is recorded in `AI_Import` and the relevant source fields are added to `Jobs`.

This tool only records/analyzes opportunities. It does not submit applications or contact recruiters.
