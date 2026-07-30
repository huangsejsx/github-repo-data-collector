#!/usr/bin/env python3
"""Collect GitHub repository metadata with the GitHub REST API.

This script uses the public Search repositories endpoint:
https://api.github.com/search/repositories

Optional authentication:
    export GITHUB_TOKEN="your_personal_access_token"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://api.github.com/search/repositories"
USER_AGENT = "github-repo-data-collector-class-project"

CSV_FIELDS = [
    "collected_at",
    "query",
    "rank",
    "id",
    "full_name",
    "name",
    "owner_login",
    "owner_type",
    "html_url",
    "description",
    "language",
    "topics",
    "stargazers_count",
    "forks_count",
    "watchers_count",
    "open_issues_count",
    "size_kb",
    "license",
    "created_at",
    "updated_at",
    "pushed_at",
    "default_branch",
    "archived",
    "fork",
    "visibility",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect GitHub repository metadata using the GitHub REST API."
    )
    parser.add_argument(
        "--query",
        default="language:python stars:>1000",
        help=(
            "GitHub search query. Examples: 'topic:machine-learning language:python', "
            "'data acquisition stars:>50', 'org:openai'."
        ),
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=100,
        help="Maximum number of repositories to collect.",
    )
    parser.add_argument(
        "--sort",
        choices=["stars", "forks", "help-wanted-issues", "updated"],
        default="stars",
        help="Sort field for repository search results.",
    )
    parser.add_argument(
        "--order",
        choices=["asc", "desc"],
        default="desc",
        help="Sort order.",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=50,
        help="Results per API page. GitHub allows up to 100.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help=(
            "Seconds to wait between page requests. If omitted, the script uses "
            "a conservative default based on whether GITHUB_TOKEN is set."
        ),
    )
    parser.add_argument(
        "--out-dir",
        default="data",
        help="Output directory for raw JSON, CSV, and metadata files.",
    )
    parser.add_argument(
        "--api-version",
        default="2026-03-10",
        help="GitHub REST API version header.",
    )
    parser.add_argument(
        "--wait-on-rate-limit",
        action="store_true",
        help="Wait and retry if GitHub returns a primary rate-limit response.",
    )
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_headers(api_version: str) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": api_version,
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def seconds_until_reset(headers: dict[str, str]) -> Optional[int]:
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after:
        try:
            return max(1, int(retry_after))
        except ValueError:
            return None

    reset = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
    if not reset:
        return None

    try:
        reset_epoch = int(reset)
    except ValueError:
        return None

    return max(1, reset_epoch - int(time.time()) + 1)


def request_json(
    params: dict[str, Any],
    headers: dict[str, str],
    wait_on_rate_limit: bool,
) -> tuple[dict[str, Any], dict[str, str]]:
    url = f"{BASE_URL}?{urlencode(params)}"
    request = Request(url, headers=headers)

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, dict(response.headers)
    except HTTPError as exc:
        response_headers = dict(exc.headers)
        body = exc.read().decode("utf-8", errors="replace")

        if exc.code in {403, 429} and wait_on_rate_limit:
            wait_seconds = seconds_until_reset(response_headers)
            if wait_seconds is not None:
                print(f"Rate limited. Waiting {wait_seconds} seconds, then retrying...")
                time.sleep(wait_seconds)
                return request_json(params, headers, wait_on_rate_limit=False)

        raise RuntimeError(
            f"GitHub API request failed with HTTP {exc.code}.\n"
            f"URL: {url}\n"
            f"Response body: {body}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Network request failed: {exc}") from exc


def flatten_repository(
    repo: dict[str, Any],
    query: str,
    rank: int,
    collected_at: str,
) -> dict[str, Any]:
    owner = repo.get("owner") or {}
    license_info = repo.get("license") or {}
    topics = repo.get("topics") or []

    return {
        "collected_at": collected_at,
        "query": query,
        "rank": rank,
        "id": repo.get("id"),
        "full_name": repo.get("full_name"),
        "name": repo.get("name"),
        "owner_login": owner.get("login"),
        "owner_type": owner.get("type"),
        "html_url": repo.get("html_url"),
        "description": repo.get("description") or "",
        "language": repo.get("language") or "",
        "topics": ";".join(topics),
        "stargazers_count": repo.get("stargazers_count"),
        "forks_count": repo.get("forks_count"),
        "watchers_count": repo.get("watchers_count"),
        "open_issues_count": repo.get("open_issues_count"),
        "size_kb": repo.get("size"),
        "license": license_info.get("spdx_id") or license_info.get("key") or "",
        "created_at": repo.get("created_at"),
        "updated_at": repo.get("updated_at"),
        "pushed_at": repo.get("pushed_at"),
        "default_branch": repo.get("default_branch"),
        "archived": repo.get("archived"),
        "fork": repo.get("fork"),
        "visibility": repo.get("visibility"),
    }


def collect_repositories(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if args.max_results < 1:
        raise ValueError("--max-results must be at least 1.")

    per_page = min(max(args.per_page, 1), 100)
    delay = args.delay
    if delay is None:
        delay = 2.1 if os.getenv("GITHUB_TOKEN") else 6.1

    headers = build_headers(args.api_version)
    collected_at = utc_now_iso()
    rows: list[dict[str, Any]] = []
    raw_pages: list[dict[str, Any]] = []
    page = 1
    total_count: Optional[int] = None
    incomplete_results: Optional[bool] = None

    while len(rows) < args.max_results:
        remaining_needed = args.max_results - len(rows)
        params = {
            "q": args.query,
            "sort": args.sort,
            "order": args.order,
            "per_page": min(per_page, remaining_needed),
            "page": page,
        }

        print(f"Requesting page {page}: {params}")
        data, response_headers = request_json(
            params=params,
            headers=headers,
            wait_on_rate_limit=args.wait_on_rate_limit,
        )

        items = data.get("items", [])
        if not isinstance(items, list):
            raise RuntimeError("Unexpected API response: 'items' is not a list.")

        total_count = data.get("total_count", total_count)
        incomplete_results = data.get("incomplete_results", incomplete_results)
        raw_pages.append(
            {
                "page": page,
                "request_params": params,
                "response_headers": {
                    key: value
                    for key, value in response_headers.items()
                    if key.lower().startswith("x-ratelimit")
                },
                "response": data,
            }
        )

        if not items:
            break

        for repo in items:
            if len(rows) >= args.max_results:
                break
            rows.append(
                flatten_repository(
                    repo=repo,
                    query=args.query,
                    rank=len(rows) + 1,
                    collected_at=collected_at,
                )
            )

        remaining_header = (
            response_headers.get("X-RateLimit-Remaining")
            or response_headers.get("x-ratelimit-remaining")
        )
        if remaining_header == "0" and len(rows) < args.max_results:
            wait_seconds = seconds_until_reset(response_headers)
            if args.wait_on_rate_limit and wait_seconds is not None:
                print(f"Rate limit remaining is 0. Waiting {wait_seconds} seconds...")
                time.sleep(wait_seconds)
            else:
                print("Rate limit remaining is 0. Stopping early.", file=sys.stderr)
                break

        page += 1
        if len(rows) < args.max_results:
            time.sleep(delay)

    metadata = {
        "collected_at": collected_at,
        "api_endpoint": BASE_URL,
        "api_version": args.api_version,
        "query": args.query,
        "sort": args.sort,
        "order": args.order,
        "requested_max_results": args.max_results,
        "actual_results": len(rows),
        "per_page": per_page,
        "delay_seconds": delay,
        "used_token": bool(os.getenv("GITHUB_TOKEN")),
        "total_count_reported_by_github": total_count,
        "incomplete_results_reported_by_github": incomplete_results,
    }

    return rows, {"metadata": metadata, "raw_pages": raw_pages}


def write_outputs(rows: list[dict[str, Any]], raw: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "repositories.csv"
    json_path = out_dir / "repositories_raw.json"
    metadata_path = out_dir / "metadata.json"

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(raw, json_file, indent=2, ensure_ascii=False)

    with metadata_path.open("w", encoding="utf-8") as metadata_file:
        json.dump(raw["metadata"], metadata_file, indent=2, ensure_ascii=False)

    print(f"Wrote {len(rows)} rows to {csv_path}")
    print(f"Wrote raw API responses to {json_path}")
    print(f"Wrote collection metadata to {metadata_path}")


def main() -> int:
    args = parse_args()
    try:
        rows, raw = collect_repositories(args)
        write_outputs(rows, raw, Path(args.out_dir))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
