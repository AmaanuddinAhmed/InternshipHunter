"""
Unstop adapter — public internship/job listings.

Best-effort adapter:
- Reads public listing pages.
- Does not log in.
- Does not submit applications.
- Fails gracefully if Unstop blocks requests or changes markup.
"""

import re

from .base import Source, get_text, strip_html


BASE_URL = "https://unstop.com/internships"


class UnstopSource(Source):
    name = "unstop"

    def search(self, queries=None, locations=None, remote=True):
        try:
            html = get_text(
                BASE_URL,
                timeout=20,
            )
        except Exception as error:  # noqa: BLE001
            self.log(f"WARNING: {error}")
            return []

        if not html:
            self.log("WARNING: empty response")
            return []

        # Unstop currently renders internship listings dynamically.
        # The public HTML returned by requests does not contain the
        # actual listing cards/URLs, so do not fabricate results.
        self.log(
            "WARNING: listings not available in server-rendered HTML; "
            "skipping this source."
        )

        return []