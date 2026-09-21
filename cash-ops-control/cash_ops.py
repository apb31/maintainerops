#!/usr/bin/env python3
"""Deterministic, stdlib-only public bounty intake and ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state.json"
CONFIG = ROOT / "sources.json"
DASHBOARD = ROOT / "dashboard.md"
STATUS_LABELS = ("lead", "qualified", "claimed", "working", "review", "blocked", "submitted", "payout", "rejected")
ROLE_PIPELINE = (
    ("Scout", "lead"), ("Verifier", "qualified"), ("Claimant", "claimed"),
    ("Builder", "working"), ("Reviewer", "review"), ("Submitter", "submitted"),
    ("Collector", "payout"), ("Closer", "rejected"),
)
MANUAL_KEYS = {"status", "verified", "accepted_payout", "collected", "spend", "notes", "owner", "tracker_issue_number"}
MONEY = re.compile(r"(?:\b(bounty|reward|payout)\b\s*(?:is\s*)?[:=\-]?\s*(?:USD\s*)?\$([\d,]+(?:\.\d{1,2})?)|(?:USD\s*)?\$([\d,]+(?:\.\d{1,2})?)\s*\b(bounty|reward|payout)\b)", re.I)
VARIABLE = re.compile(r"\b(up\s+to|from|starting\s+at|pool|shared|total\s+prize)\b", re.I)
TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean(value: object, limit: int = 1200) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def canonical_url(url: str) -> str:
    p = urllib.parse.urlsplit(url.strip())
    scheme = "https" if p.scheme in ("http", "https") else p.scheme.lower()
    host = (p.hostname or "").lower()
    port = f":{p.port}" if p.port and not (scheme == "https" and p.port == 443) else ""
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urllib.parse.urlencode(sorted((k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING))
    return urllib.parse.urlunsplit((scheme, host + port, path, query, ""))


def item_id(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode()).hexdigest()[:20]


def advertised_payout(text: str) -> float | None:
    for match in MONEY.finditer(text):
        context = text[max(0, match.start() - 35):match.end() + 35]
        if VARIABLE.search(context):
            continue
        raw = match.group(2) or match.group(3)
        value = float(raw.replace(",", ""))
        if 0 < value <= 10_000_000:
            return value
    return None


def candidate(url: str, title: str, summary: str, source: str, opened: bool = True) -> dict:
    url = canonical_url(url)
    title, summary = clean(title, 240), clean(summary)
    payout = advertised_payout(f"{title} {summary}")
    score = min(100, 20 + (45 if payout is not None else 0) + (15 if opened else 0))
    return {
        "id": item_id(url), "url": url, "title": title or url, "summary": summary,
        "source": source, "open": bool(opened), "advertised_payout": payout,
        "payout_basis": "explicit fixed USD text" if payout is not None else "not verified",
        "score": score, "status": "lead", "verified": False,
        "accepted_payout": None, "collected": 0, "first_seen": now(), "last_seen": now(),
    }


def parse_github(payload: bytes, source: str) -> list[dict]:
    data = json.loads(payload)
    return [candidate(row.get("html_url", ""), row.get("title", ""), row.get("body", ""), source, row.get("state") == "open")
            for row in data.get("items", []) if row.get("html_url")]


def parse_github_issue(payload: bytes, source: str) -> list[dict]:
    row = json.loads(payload)
    return [candidate(row.get("html_url", ""), row.get("title", ""), row.get("body", ""), source, row.get("state") == "open")] if row.get("html_url") else []


def _node_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1].lower() in names and child.text:
            return child.text
    return ""


def parse_rss(payload: bytes, source: str) -> list[dict]:
    root = ET.fromstring(payload)
    rows = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() not in ("item", "entry"):
            continue
        link = _node_text(node, ("link",))
        if not link:
            for child in node:
                if child.tag.rsplit("}", 1)[-1].lower() == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        if link:
            rows.append(candidate(link, _node_text(node, ("title",)), _node_text(node, ("description", "summary", "content")), source))
    return rows


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req.has_header("Authorization") and (urllib.parse.urlsplit(req.full_url).scheme, urllib.parse.urlsplit(req.full_url).netloc) != (urllib.parse.urlsplit(newurl).scheme, urllib.parse.urlsplit(newurl).netloc):
            raise urllib.error.HTTPError(newurl, 403, "refused authenticated cross-origin redirect", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def github_headers(url: str, token: str) -> dict:
    return {"Authorization": f"Bearer {token}"} if token and urllib.parse.urlsplit(url).scheme == "https" and urllib.parse.urlsplit(url).netloc == "api.github.com" else {}


def request(url: str, headers: dict, timeout: int, method: str = "GET", body: dict | None = None) -> tuple[int, bytes, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": "cash-ops-control/1", "Accept": "application/vnd.github+json", **headers})
    try:
        with urllib.request.build_opener(SafeRedirect).open(req, timeout=max(2, min(timeout, 30))) as res:
            payload = res.read(5_000_001)
            if len(payload) > 5_000_000:
                raise ValueError("response exceeds 5 MB")
            return res.status, payload, dict(res.headers)
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return 304, b"", dict(exc.headers)
        detail = clean(exc.read(500), 500)
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def load(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def merge_items(existing: list[dict], found: list[dict]) -> list[dict]:
    merged = {row["id"]: dict(row) for row in existing}
    for fresh in found:
        old = merged.get(fresh["id"], {})
        if "verified" not in old and "human_verified" in old:
            old["verified"] = bool(old["human_verified"])
        kept = {key: old[key] for key in MANUAL_KEYS if key in old}
        fresh["first_seen"] = old.get("first_seen", fresh["first_seen"])
        merged[fresh["id"]] = {**fresh, **kept}
    return sorted(merged.values(), key=lambda row: (row.get("status", "lead"), row.get("id", "")))


def scan(config_path: Path = CONFIG, state_path: Path = STATE) -> dict:
    cfg = load(config_path, {})
    state = load(state_path, {"version": 1, "items": [], "cache": {}, "observations": [], "errors": []})
    token = os.getenv("GITHUB_TOKEN", "")
    timeout = int(cfg.get("timeout_seconds", 15))
    found, observations, errors = [], [], []
    sources = []
    for row in cfg.get("github_searches", []):
        query = urllib.parse.urlencode({"q": row["query"], "per_page": min(int(row.get("limit", 30)), 50), "sort": "updated"})
        sources.append((row["name"], f"https://api.github.com/search/issues?{query}", parse_github))
    for row in cfg.get("rss", []):
        if row.get("enabled", True): sources.append((row["name"], row["url"], parse_rss))
    for row in state.get("items", []):
        match = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+)/issues/(\d+)", row.get("url", ""))
        if match and row.get("status", "lead") not in ("payout", "rejected"):
            owner, repo, number = match.groups()
            sources.append((f"track:{row['id']}", f"https://api.github.com/repos/{owner}/{repo}/issues/{number}",
                            lambda payload, _name, original=row.get("source", "tracked GitHub issue"): parse_github_issue(payload, original)))
        if len(sources) >= len(cfg.get("github_searches", [])) + len(cfg.get("rss", [])) + 10: break
    for name, url, parser in sources:
        cache = state.get("cache", {}).get(name, {})
        headers = github_headers(url, token)
        if cache.get("etag"): headers["If-None-Match"] = cache["etag"]
        if cache.get("last_modified"): headers["If-Modified-Since"] = cache["last_modified"]
        try:
            status, payload, response_headers = request(url, headers, timeout)
            if status == 304:
                observations.append({"source": name, "at": now(), "result": "not modified"})
                continue
            rows = parser(payload, name); found.extend(rows)
            state.setdefault("cache", {})[name] = {"etag": response_headers.get("ETag"), "last_modified": response_headers.get("Last-Modified")}
            observations.append({"source": name, "at": now(), "result": "ok", "count": len(rows)})
        except Exception as exc:
            errors.append({"source": name, "at": now(), "error": clean(exc, 500)})
    state["items"] = merge_items(state.get("items", []), found)
    state["observations"], state["errors"], state["last_scan"] = observations, errors, now()
    state["scan_health"] = "failed" if sources and errors and not observations else "partial" if errors else "ok"
    state["scan_run"] = {"at": state["last_scan"], "status": state["scan_health"]}
    atomic_json(state_path, state)
    write_dashboard(state, state_path.parent / "dashboard.md")
    return state


def money(value: object) -> float:
    value = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0
    return value if math.isfinite(value) and value >= 0 else 0.0


def next_action(items: list[dict]) -> str:
    order = {"lead": "Verify", "qualified": "Claim", "claimed": "Start", "working": "Finish", "review": "Review", "blocked": "Unblock", "submitted": "Check response/acceptance"}
    priority = {"working": 7, "review": 6, "submitted": 5, "claimed": 4, "blocked": 3, "qualified": 2, "lead": 1}
    rows = [x for x in items if x.get("status") in order]
    if not rows: return "No active lead. Review source errors or wait for the next scan."
    row = max(rows, key=lambda x: (x.get("status") in ("claimed", "working", "review", "blocked", "submitted") and money(x.get("accepted_payout")) > 0,
                                   priority[x["status"]], bool(x.get("verified")), x.get("score", 0)))
    return f"{order[row['status']]}: [{clean(row.get('title'), 100)}]({row.get('url')})"


def write_dashboard(state: dict, path: Path = DASHBOARD) -> None:
    items = state.get("items", [])
    advertised = sum(money(x.get("advertised_payout")) for x in items if x.get("status") != "rejected" and x.get("open", True))
    accepted = sum(money(x.get("accepted_payout")) for x in items)
    collected = sum(money(x.get("collected")) for x in items)
    spend = sum(money(x.get("spend")) for x in items)
    pending = sum(max(0, money(x.get("accepted_payout")) - money(x.get("collected"))) for x in items)
    active = sum(money(x.get("accepted_payout")) for x in items if x.get("status") in ("claimed", "working", "review", "blocked", "submitted"))
    claims = sum(x.get("status") in ("claimed", "working", "review", "submitted") or (x.get("status") == "blocked" and x.get("application_submitted", False)) for x in items)
    counts = {status: sum(x.get("status") == status for x in items) for status in STATUS_LABELS}
    lines = ["# Cash Ops Control", "", f"Updated: {state.get('last_scan', 'never')}  ", f"Scan health: **{state.get('scan_health', 'not run')}**", "", "## Financial ledger", "",
             "| Measure | USD | Meaning |", "|---|---:|---|", f"| Advertised | ${advertised:,.2f} | Public fixed amounts observed; not earned |",
             f"| Accepted | ${accepted:,.2f} | Operator-recorded agreed payouts; not yet cash |", f"| Collected | ${collected:,.2f} | Operator-recorded money received |",
             f"| Pending payout | ${pending:,.2f} | Accepted less recorded collection, floored per item |", f"| Active paid work | ${active:,.2f} | Accepted value in active work stages |",
             f"| Spend | ${spend:,.2f} | Operator-recorded costs |", f"| Net | ${collected - spend:,.2f} | Recorded collection less recorded spend |",
             "", f"Applications/claims in progress: **{claims}**  ", f"Best next action: {next_action(items)}  ",
             f"External worker status: latest scan run **{state.get('scan_health', 'not run')}** at {state.get('last_scan', 'unavailable')}; execution host heartbeat is not available.  ",
             "Work quota: **unknown**. This program cannot inspect ChatGPT Work usage or cost.", "", "## Pipeline", "",
             "| Status | Count |", "|---|---:|"]
    lines += [f"| {s} | {counts[s]} |" for s in STATUS_LABELS]
    lines += ["", "## Source observations", ""]
    lines += [f"- {clean(x.get('source'))}: {clean(x.get('result'))} ({x.get('count', 'n/a')}) at {clean(x.get('at'))}" for x in state.get("observations", [])] or ["- No scans recorded."]
    lines += ["", "## Errors", ""]
    lines += [f"- {clean(x.get('source'))}: {clean(x.get('error'))} at {clean(x.get('at'))}" for x in state.get("errors", [])] or ["- None recorded."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def api(repo: str, endpoint: str, method: str, body: dict | None, token: str) -> dict:
    status, payload, _ = request(f"https://api.github.com/repos/{repo}{endpoint}", {"Authorization": f"Bearer {token}"}, 20, method, body)
    return json.loads(payload) if payload else {"status": status}


def sync_issues(config_path: Path = CONFIG, state_path: Path = STATE) -> None:
    cfg, state = load(config_path, {}), load(state_path, {})
    repo, token = cfg.get("issue_repo", ""), os.getenv("GITHUB_TOKEN", "")
    if not repo or not token: raise RuntimeError("issue_repo and GITHUB_TOKEN are required")
    if os.getenv("GITHUB_REPOSITORY", repo).lower() != repo.lower(): raise RuntimeError("issue_repo must equal GITHUB_REPOSITORY")
    colors = {s: ("1f883d" if s == "payout" else "8250df" if s in ("qualified", "claimed", "working") else "d1242f" if s in ("blocked", "rejected") else "0969da") for s in STATUS_LABELS}
    for label, color in colors.items():
        try: api(repo, "/labels", "POST", {"name": label, "color": color}, token)
        except RuntimeError as exc:
            if "HTTP 422" not in str(exc): raise
    tracked = api(repo, "/issues?state=all&per_page=100", "GET", None, token)
    markers = {}
    for issue in tracked if isinstance(tracked, list) else []:
        found = re.search(r"<!-- cash-ops:([a-f0-9]{20}) -->", issue.get("body") or "")
        if found: markers[found.group(1)] = issue["number"]
    eligible = [row for row in state.get("items", []) if row.get("status", "lead") not in ("payout", "rejected") and (row.get("verified") or row.get("status") != "lead")]
    for row in sorted(eligible, key=lambda x: (x.get("score", 0), money(x.get("advertised_payout"))), reverse=True)[:5]:
        status = row.get("status", "lead") if row.get("status") in STATUS_LABELS else "lead"
        body = f"<!-- cash-ops:{row['id']} -->\nPublic source: {row['url']}\n\nAdvertised payout: {row.get('advertised_payout')} USD\nVerification: {'operator verified' if row.get('verified') else 'required before outreach or claim'}\nScore: {row.get('score', 0)}/100\n"
        data = {"title": f"[Cash Ops] {clean(row.get('title'), 180)}", "body": body, "labels": [status]}
        number = row.get("tracker_issue_number") or markers.get(row["id"])
        result = api(repo, f"/issues/{number}" if number else "/issues", "PATCH" if number else "POST", data, token)
        if not number:
            row["tracker_issue_number"] = result["number"]
            atomic_json(state_path, state)
        elif not row.get("tracker_issue_number"):
            row["tracker_issue_number"] = number
            atomic_json(state_path, state)
    atomic_json(state_path, state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("scan", "report", "sync-issues"), nargs="?", default="scan")
    args = parser.parse_args()
    try:
        if args.command == "scan": scan()
        elif args.command == "report": write_dashboard(load(STATE, {}))
        else: sync_issues()
        return 0
    except Exception as exc:
        print(f"cash-ops-control: {exc}", file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
