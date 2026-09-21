from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

API = "https://api.github.com"


def _request(path: str) -> Any:
    token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "maintainerops/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(f"{API}{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def repo(owner_repo: str) -> dict[str, Any]:
    return _request(f"/repos/{owner_repo}")


def issues(owner_repo: str, state: str = "open", per_page: int = 100) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"state": state, "per_page": per_page})
    data = _request(f"/repos/{owner_repo}/issues?{query}")
    return [item for item in data if "pull_request" not in item]


def pulls(owner_repo: str, state: str = "open", per_page: int = 100) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"state": state, "per_page": per_page})
    return _request(f"/repos/{owner_repo}/pulls?{query}")


def latest_release(owner_repo: str) -> dict[str, Any] | None:
    try:
        return _request(f"/repos/{owner_repo}/releases/latest")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def age_days(iso_timestamp: str) -> int:
    dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days
