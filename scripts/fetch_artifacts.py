from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

from github import Auth, Github, GithubException, RateLimitExceededException


T = TypeVar("T")

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "artifacts"
LIMIT = 200
MAX_RETRIES = 6


def retry_request(
    operation: Callable[[], T],
    github: Github,
) -> T:
    """Retry GitHub API operations after rate limits or transient failures."""
    for attempt in range(MAX_RETRIES):
        try:
            return operation()

        except RateLimitExceededException:
            try:
                reset = github.get_rate_limit().core.reset.timestamp()
                delay = max(1, reset - time.time() + 2)
            except Exception:
                delay = min(60, 2 ** (attempt + 1))

        except GithubException as exc:
            if exc.status not in {403, 429, 500, 502, 503, 504}:
                raise

            headers = getattr(exc, "headers", {}) or {}
            retry_after = headers.get("Retry-After")

            if retry_after is not None:
                try:
                    delay = max(1, int(retry_after))
                except (ValueError, TypeError):
                    delay = min(60, 2 ** (attempt + 1))
            elif exc.status in {403, 429}:
                try:
                    reset = github.get_rate_limit().core.reset.timestamp()
                    delay = max(1, reset - time.time() + 2)
                except Exception:
                    delay = min(60, 2 ** (attempt + 1))
            else:
                delay = min(60, 2 ** (attempt + 1))

        if attempt == MAX_RETRIES - 1:
            raise RuntimeError(
                "GitHub request failed after repeated retries"
            )

        print(f"GitHub request failed; retrying in {delay:.0f}s...")
        time.sleep(delay)

    raise RuntimeError("GitHub request failed")


def iso_datetime(value: datetime) -> str:
    """Serialize timestamps consistently in UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).isoformat()


def load_cache(path: Path) -> tuple[list[dict], set[tuple[str, int]]]:
    """Load cached artifacts and index them by kind and number."""
    if not path.exists():
        return [], set()

    with path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError(f"Expected a JSON list in {path}")

    existing = {
        (record["kind"], int(record["number"]))
        for record in records
    }

    return records, existing


def fetch_artifacts(owner: str, name: str) -> Path:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is missing. Export a GitHub personal access token."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{owner}__{name}.json"

    github = Github(auth=Auth.Token(token))

    try:
        repo = retry_request(
            lambda: github.get_repo(f"{owner}/{name}"),
            github,
        )

        records, existing = load_cache(output_path)
        print(f"Cached artifacts: {len(existing)}")

        # Issues endpoint includes PRs; exclude them from the issue count.
        issues = retry_request(
            lambda: repo.get_issues(
                state="closed",
                sort="created",
                direction="desc",
                per_page=100,
            ),
            github,
        )

        issue_count = 0
        processed_issues = 0
        page = 0

        while processed_issues < LIMIT:
            batch = retry_request(
                lambda: issues.get_page(page),
                github,
            )
            if not batch:
                break

            for item in batch:
                if item.pull_request is not None:
                    continue

                # Count every eligible issue encountered, including cached ones.
                processed_issues += 1
                key = ("issue", item.number)

                if key not in existing:
                    records.append(
                        {
                            "kind": "issue",
                            "number": item.number,
                            "title": item.title or "",
                            "body": item.body or "",
                            "created_at": iso_datetime(item.created_at),
                            "files": [],
                        }
                    )
                    existing.add(key)
                    issue_count += 1

                if processed_issues >= LIMIT:
                    break

            page += 1

        print(
            f"New issues cached: {issue_count}; "
            f"recent issues examined: {processed_issues}"
        )

        # Fetch closed PRs, retaining only merged ones.
        pulls = retry_request(
            lambda: repo.get_pulls(
                state="closed",
                sort="created",
                direction="desc",
                base=None,
                per_page=100,
            ),
            github,
        )

        pr_count = 0
        processed_prs = 0
        page = 0

        while processed_prs < LIMIT:
            batch = retry_request(
                lambda: pulls.get_page(page),
                github,
            )
            if not batch:
                break

            for pr in batch:
                if pr.merged_at is None:
                    continue

                # Count merged PRs even when their details are already cached.
                processed_prs += 1
                key = ("pr", pr.number)

                # Never re-download changed files for cached PRs.
                if key not in existing:
                    files: list[str] = []
                    file_page = 0
                    pr_files = retry_request(
                        lambda: pr.get_files(),
                        github,
                    )

                    while True:
                        file_batch = retry_request(
                            lambda: pr_files.get_page(file_page),
                            github,
                        )
                        if not file_batch:
                            break

                        files.extend(item.filename for item in file_batch)
                        file_page += 1

                    records.append(
                        {
                            "kind": "pr",
                            "number": pr.number,
                            "title": pr.title or "",
                            "body": pr.body or "",
                            "created_at": iso_datetime(pr.created_at),
                            "files": sorted(set(files)),
                        }
                    )
                    existing.add(key)
                    pr_count += 1

                if processed_prs >= LIMIT:
                    break

            page += 1

        print(
            f"New merged PRs cached: {pr_count}; "
            f"recent merged PRs examined: {processed_prs}"
        )

        # Write atomically so a failed write does not corrupt the existing cache.
        temp_path = output_path.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(output_path)

        print(f"Saved {len(records)} artifacts to {output_path}")
        return output_path

    finally:
        github.close()


def main() -> int:
    if len(sys.argv) != 3:
        print(
            f"Usage: {sys.argv[0]} <owner> <repo>",
            file=sys.stderr,
        )
        return 2

    owner, name = sys.argv[1:3]

    try:
        fetch_artifacts(owner, name)
    except (RuntimeError, GithubException, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
