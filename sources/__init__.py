"""
Source registry.

`enabled_sources()` returns every adapter that is turned on and configured
(i.e. its API key or config file is present). A source that is not
configured is skipped, not an error — so you can add keys incrementally.
"""

from dotenv import load_dotenv

# Load .env as soon as the sources package is imported, so adapters can read
# their API keys from the environment.
load_dotenv()

from .ats import WatchlistSource  # noqa: E402
from .jooble import JoobleSource  # noqa: E402
from .adzuna import AdzunaSource  # noqa: E402
from .internshala import InternshalaSource  # noqa: E402
from .unstop import UnstopSource  # noqa: E402
from .hn_whoishiring import HNWhoIsHiringSource  # noqa: E402

# Every known adapter, in the order they should run. The watchlist goes
# first so that when the same role also shows up on a job board, the
# careers-page copy (full description, direct apply link) is the one kept.
ALL_SOURCES = [
    WatchlistSource(),
    JoobleSource(),
    AdzunaSource(),
    InternshalaSource(),
    UnstopSource(),
    HNWhoIsHiringSource(),
]


def enabled_sources():
    active = []
    for source in ALL_SOURCES:
        if not source.enabled:
            continue
        if not source.is_configured():
            print(f"  (skipping {source.name}: not configured)")
            continue
        active.append(source)
    return active
