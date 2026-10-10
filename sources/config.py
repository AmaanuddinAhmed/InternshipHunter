"""
Central search configuration shared by the source adapters.

Tune these to change what the whole system looks for.
"""

# Role search phrases (used by keyword APIs like Jooble and Adzuna).
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

# Locations for India-focused, keyword-based sources.
# Kept modest to respect free-tier API quotas; expand as needed.
LOCATIONS = [
    "Bangalore",
    "Remote",
]
