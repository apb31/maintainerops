from __future__ import annotations

from typing import Any

from .github import age_days


def build_report(
    repo_data: dict[str, Any],
    issue_data: list[dict[str, Any]],
    pull_data: list[dict[str, Any]],
    release: dict[str, Any] | None,
    stale_days: int,
) -> dict[str, Any]:
    stale_issues = [item for item in issue_data if age_days(item["updated_at"]) >= stale_days]
    stale_pulls = [item for item in pull_data if age_days(item["updated_at"]) >= stale_days]

    release_age = None
    if release and release.get("published_at"):
        release_age = age_days(release["published_at"])

    return {
        "repository": repo_data.get("full_name"),
        "stars": repo_data.get("stargazers_count", 0),
        "forks": repo_data.get("forks_count", 0),
        "open_issues": len(issue_data),
        "open_pull_requests": len(pull_data),
        "stale_issues": len(stale_issues),
        "stale_pull_requests": len(stale_pulls),
        "latest_release": release.get("tag_name") if release else None,
        "latest_release_age_days": release_age,
        "default_branch": repo_data.get("default_branch"),
        "archived": repo_data.get("archived", False),
    }
