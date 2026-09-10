"""
YC adapter — best-effort public startup jobs source.

YC's public jobs endpoint may change or disappear.
This adapter must fail gracefully and never break discovery.
"""

from .base import Source, get_text, strip_html

BASE_URL = "https://www.ycombinator.com/jobs"


class YCSource(Source):
    name = "yc"

    def search(self, queries=None, locations=None, remote=True):
        try:
            html = get_text(
                BASE_URL,
                timeout=20,
            )
        except Exception as error:  # noqa: BLE001
            self.log(f"WARNING: YC unavailable: {error}")
            return []

        if not html:
            self.log("WARNING: YC returned empty response.")
            return []

        # The old public jobs page is no longer reliably available.
        # Do not attempt aggressive scraping here.
        self.log(
            "WARNING: YC jobs listings are not currently available "
            "through the public endpoint; skipping."
        )

        return []