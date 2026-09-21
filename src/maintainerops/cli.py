from __future__ import annotations

import argparse
import json
import sys

from .formatters import report_to_csv
from .github import issues, latest_release, pulls, repo
from .report import build_report


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="maintainerops",
        description="Generate a compact maintenance report for a public GitHub repository.",
    )
    p.add_argument("repository", help="GitHub repository in owner/name form")
    p.add_argument("--stale-days", type=int, default=30, help="Age in days used to mark work as stale")
    output = p.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    output.add_argument("--csv", action="store_true", help="Output a single-row CSV report")
    return p


def main() -> None:
    args = parser().parse_args()

    if "/" not in args.repository:
        raise SystemExit("repository must be in owner/name form")

    try:
        repo_data = repo(args.repository)
        issue_data = issues(args.repository)
        pull_data = pulls(args.repository)
        release_data = latest_release(args.repository)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

    report = build_report(
        repo_data,
        issue_data,
        pull_data,
        release_data,
        args.stale_days,
    )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    if args.csv:
        print(report_to_csv(report), end="")
        return

    print(f"Repository: {report['repository']}")
    print(f"Stars: {report['stars']} | Forks: {report['forks']}")
    print(f"Open issues: {report['open_issues']} ({report['stale_issues']} stale)")
    print(f"Open PRs: {report['open_pull_requests']} ({report['stale_pull_requests']} stale)")
    release = report["latest_release"] or "none"
    if report["latest_release_age_days"] is not None:
        release += f" ({report['latest_release_age_days']} days ago)"
    print(f"Latest release: {release}")


if __name__ == "__main__":
    main()
