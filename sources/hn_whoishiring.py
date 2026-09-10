"""
Hacker News "Who is Hiring?" adapter.

Uses the official Algolia Hacker News Search API.
Keyless and public.

We search recent "Who is Hiring?" threads, then inspect their comments
for internship / entry-level software-development opportunities.
"""

from .base import Source, get_json, strip_html, mentions_any


ENTRY = [
    "intern",
    "internship",
    "junior",
    "graduate",
    "new grad",
    "entry level",
    "entry-level",
    "trainee",
    "student",
]

DEV = [
    "developer",
    "engineer",
    "software",
    "full stack",
    "fullstack",
    "backend",
    "back-end",
    "frontend",
    "front-end",
    "python",
    "java",
    "javascript",
    "typescript",
    "node",
    "react",
    "angular",
    "django",
    "flask",
    "fastapi",
    "devops",
    "sde",
]

API = "https://hn.algolia.com/api/v1"

MAX_THREADS = 3
MAX_COMMENTS_PER_THREAD = 100


class HNWhoIsHiringSource(Source):
    name = "hn_whoishiring"

    def search(self, queries=None, locations=None, remote=True):
        jobs = []
        seen = set()

        # --------------------------------------------------
        # Find recent "Who is Hiring?" threads.
        # --------------------------------------------------

        try:
            data = get_json(
                f"{API}/search_by_date",
                params={
                    "query": "Ask HN: Who is hiring?",
                    "tags": "story",
                    "hitsPerPage": MAX_THREADS,
                },
            )
        except Exception as error:  # noqa: BLE001
            self.log(f"ERROR finding hiring threads: {error}")
            return []

        threads = data.get("hits") or []

        if not threads:
            self.log("No Who Is Hiring threads found.")
            return []

        # --------------------------------------------------
        # Inspect comments from each hiring thread.
        # --------------------------------------------------

        for thread in threads:

            thread_id = thread.get("objectID")

            if not thread_id:
                continue

            try:
                comments = get_json(
                    f"{API}/search",
                    params={
                        "tags": f"comment,story_{thread_id}",
                        "hitsPerPage": MAX_COMMENTS_PER_THREAD,
                    },
                )
            except Exception as error:  # noqa: BLE001
                self.log(
                    f"ERROR reading thread {thread_id}: {error}"
                )
                continue

            hits = comments.get("hits") or []

            for comment in hits:

                text = strip_html(
                    comment.get("comment_text") or ""
                )

                if not text:
                    continue

                # --------------------------------------------------
                # HN hiring comments are free-form text.
                # Require both an entry-level signal and
                # software-development signal.
                # --------------------------------------------------

                if not mentions_any(text, ENTRY):
                    continue

                if not mentions_any(text, DEV):
                    continue

                # --------------------------------------------------
                # Prefer the HN comment URL as the identity.
                # --------------------------------------------------

                comment_id = comment.get("objectID")

                if comment_id:
                    url = (
                        "https://news.ycombinator.com/item?id="
                        f"{comment_id}"
                    )
                else:
                    url = ""

                if url and url in seen:
                    continue

                if url:
                    seen.add(url)

                # --------------------------------------------------
                # Try to extract a useful first line as the title.
                # HN comments usually begin with company / role info.
                # --------------------------------------------------

                lines = [
                    line.strip()
                    for line in text.splitlines()
                    if line.strip()
                ]

                first_line = lines[0] if lines else "Software Internship"

                # Keep the title reasonably short.
                title = first_line[:180]

                # Company extraction is intentionally conservative.
                # HN comments do not provide a reliable structured
                # company field.
                company = "HN Who Is Hiring"

                # --------------------------------------------------
                # Remote / location detection.
                # --------------------------------------------------

                remote_signal = mentions_any(
                    text,
                    [
                        "remote",
                        "work from home",
                        "wfh",
                        "distributed",
                    ],
                )

                location = "Remote" if remote_signal else "See job description"

                # --------------------------------------------------
                # Posted timestamp.
                # --------------------------------------------------

                posted = str(
                    comment.get("created_at") or ""
                )

                jobs.append(
                    self.normalize(
                        title=title,
                        company=company,
                        url=url,
                        location=location,
                        job_type="internship",
                        snippet=text[:400],
                        description=text,
                        posted=posted,
                        remote=remote_signal,
                        origin="hn_whoishiring",
                        query="HN Who Is Hiring internship software",
                    )
                )

        return jobs