"""
Source registry.

`enabled_sources()` returns every adapter that is turned on and configured
(i.e. its API key is present). A source with a missing key is skipped, not an
error — so you can add keys incrementally.
"""

from dotenv import load_dotenv

# Load .env as soon as the sources package is imported, so adapters can read
# their API keys from the environment.
load_dotenv()

from .jooble import JoobleSource  # noqa: E402
from .adzuna import AdzunaSource  # noqa: E402
from .remotive import RemotiveSource  # noqa: E402
from .remoteok import RemoteOKSource  # noqa: E402
from .arbeitnow import ArbeitnowSource  # noqa: E402
from .themuse import TheMuseSource  # noqa: E402
from .jobicy import JobicySource  # noqa: E402


# Every known adapter, in the order they should run.
ALL_SOURCES = [
    JoobleSource(),
    AdzunaSource(),
    RemotiveSource(),
    RemoteOKSource(),
    ArbeitnowSource(),
    TheMuseSource(),
    JobicySource(),
]


def enabled_sources():
    active = []
    for source in ALL_SOURCES:
        if not source.enabled:
            continue
        if not source.is_configured():
            print(f"  (skipping {source.name}: not configured — missing API key)")
            continue
        active.append(source)
    return active
