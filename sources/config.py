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

# Larger set of Indian metros, available for sources that can afford more calls.
INDIA_METROS = [
    "Bangalore",
    "Hyderabad",
    "Pune",
    "Delhi",
    "Mumbai",
    "Chennai",
]

# Short terms used by remote boards that filter by keyword/level.
ENTRY_TERMS = ["intern", "internship", "graduate", "trainee", "junior"]
