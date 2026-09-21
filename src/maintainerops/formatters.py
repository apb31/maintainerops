from __future__ import annotations

import csv
import io
from typing import Any

CSV_FIELDS = [
    "repository",
    "stars",
    "forks",
    "open_issues",
    "open_pull_requests",
    "stale_issues",
    "stale_pull_requests",
    "latest_release",
    "latest_release_age_days",
    "default_branch",
    "archived",
]

def report_to_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerow({field: report.get(field) for field in CSV_FIELDS})
    return buffer.getvalue()
