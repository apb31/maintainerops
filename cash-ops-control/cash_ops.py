#!/usr/bin/env python3
"""Deterministic, stdlib-only public bounty intake and ledger."""
from __future__ import annotations

import argparse
import email.utils
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state.json"
CONFIG = ROOT / "sources.json"
DASHBOARD = ROOT / "dashboard.md"
QUEUE = ROOT / "queue.json"
STATUS_LABELS = ("lead", "qualified", "claimed", "working", "review", "blocked", "submitted", "payout", "rejected")
ROLE_PIPELINE = (
    ("Scout", "lead"), ("Verifier", "qualified"), ("Claimant", "claimed"),
    ("Builder", "working"), ("Reviewer", "review"), ("Submitter", "submitted"),
    ("Collector", "payout"), ("Closer", "rejected"),
)
MANUAL_KEYS = {"status", "verified", "accepted_payout", "collected", "spend", "notes", "owner", "tracker_issue_number"}
MAX_QUEUE_JOBS = 5
DEFAULT_COOLDOWN_HOURS = 72
MONEY = re.compile(r"(?:\b(bounty|reward|payout)\b\s*(?:is\s*)?[:=\-]?\s*(?:USD\s*)?\$([\d,]+(?:\.\d{1,2})?)|(?:USD\s*)?\$([\d,]+(?:\.\d{1,2})?)\s*\b(bounty|reward|payout)\b)", re.I)
VARIABLE = re.compile(r"\b(up\s+to|from|starting\s+at|pool|shared|total\s+prize)\b", re.I)
TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


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


def canonical_topic_url(url: str) -> str:
    """Normalize feed links and collapse Discourse post links to their topic."""
    url = canonical_url(url)
    parsed = urllib.parse.urlsplit(url)
    match = re.fullmatch(r"(/t/[^/]+/\d+)(?:/\d+)?", parsed.path)
    path = match.group(1) if match else parsed.path
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


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


def candidate(url: str, title: str, summary: str, source: str, opened: bool = True,
              source_updated_at: str | None = None, source_comments: int | None = None) -> dict:
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
        "source_updated_at": clean(source_updated_at, 80) or None,
        "source_comments": source_comments if isinstance(source_comments, int) and source_comments >= 0 else None,
    }


def parse_github(payload: bytes, source: str) -> list[dict]:
    data = json.loads(payload)
    return [candidate(row.get("html_url", ""), row.get("title", ""), row.get("body", ""), source, row.get("state") == "open",
                      row.get("updated_at"), row.get("comments"))
            for row in data.get("items", []) if row.get("html_url")]


def parse_github_issue(payload: bytes, source: str) -> list[dict]:
    row = json.loads(payload)
    return [candidate(row.get("html_url", ""), row.get("title", ""), row.get("body", ""), source, row.get("state") == "open",
                      row.get("updated_at"), row.get("comments"))] if row.get("html_url") else []


def _node_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1].lower() in names and child.text:
            return child.text
    return ""


def parse_feed_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _feed_published_at(node: ET.Element) -> datetime | None:
    """Prefer original publication fields over mutable Atom update timestamps."""
    for name in ("pubdate", "published", "date", "updated"):
        parsed = parse_feed_timestamp(_node_text(node, (name,)))
        if parsed:
            return parsed
    return None


def parse_rss(payload: bytes, source: str, rules: dict | None = None, as_of: datetime | None = None) -> list[dict]:
    root = ET.fromstring(payload)
    rules = rules or {}
    buyer_signals = [clean(value).casefold() for value in rules.get("title_buyer_signals", []) if clean(value)]
    seller_exclusions = [clean(value).casefold() for value in rules.get("title_seller_exclusions", []) if clean(value)]
    max_age = rules.get("max_age_days")
    reference = as_of or datetime.now(timezone.utc)
    reference = reference.replace(tzinfo=reference.tzinfo or timezone.utc).astimezone(timezone.utc)
    rows = {}
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() not in ("item", "entry"):
            continue
        title = _node_text(node, ("title",))
        folded = clean(title).casefold()
        if seller_exclusions and any(term in folded for term in seller_exclusions):
            continue
        if buyer_signals and not any(term in folded for term in buyer_signals):
            continue
        published = _feed_published_at(node)
        if max_age is not None and (published is None or published < reference - timedelta(days=max(0, float(max_age))) or published > reference):
            continue
        link = _node_text(node, ("link",))
        if not link:
            for child in node:
                if child.tag.rsplit("}", 1)[-1].lower() == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        if link:
            summary = _node_text(node, ("description", "summary", "content"))
            row = candidate(canonical_topic_url(link), title, summary, source)
            if "summary_max_chars" in rules:
                row["summary"] = clean(summary, max(0, int(rules["summary_max_chars"])))
            if published:
                row["published_at"] = published.isoformat()
            rows.setdefault(row["id"], row)
    limit = max(0, int(rules["max_items"])) if "max_items" in rules else None
    return list(rows.values())[:limit]


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
        # Start with the old record so execution checkpoints and future manual
        # fields survive. Fresh discovery data replaces only scanner-owned keys.
        kept = dict(old)
        kept.update(fresh)
        for key in MANUAL_KEYS:
            if key in old:
                kept[key] = old[key]
        fresh["first_seen"] = old.get("first_seen", fresh["first_seen"])
        kept["first_seen"] = fresh["first_seen"]
        merged[fresh["id"]] = kept
    return sorted(merged.values(), key=lambda row: (row.get("status", "lead"), row.get("id", "")))


def source_fingerprint(item: dict) -> str:
    """Fingerprint only material source facts, excluding scan timestamps and operator data."""
    material = {key: item.get(key) for key in ("url", "title", "summary", "source", "open", "advertised_payout", "payout_basis", "source_updated_at", "source_comments")}
    encoded = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()[:24]


def job_id(item: dict, kind: str) -> str:
    return f"{kind}-{item['id']}"


def _job(item: dict, kind: str, role: str, action: str, rank: int) -> dict:
    return {
        "id": job_id(item, kind), "item_id": item["id"], "source_url": item["url"],
        "source_fingerprint": source_fingerprint(item), "kind": kind, "role": role,
        "status": item.get("status", "lead"), "priority": rank, "safe_next_action": action,
    }


def build_queue(state: dict, at: datetime | None = None, max_jobs: int = MAX_QUEUE_JOBS) -> tuple[dict, bool]:
    """Build the bounded work queue and expire stale leases in state."""
    at = (at or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    changed = False
    accepted, followups, verifications = [], [], []
    accepted_actions = {
        "qualified": ("Claimant", "Apply or claim through the official source using only the verified assignment rules."),
        "claimed": ("Builder", "Work only on the verified, accepted scope recorded for this source."),
        "working": ("Builder", "Continue the verified, accepted scope and save a reviewable checkpoint."),
        "review": ("Reviewer", "Review the completed work against the verified source requirements."),
    }
    for item in state.get("items", []):
        status, execution = item.get("status", "lead"), item.setdefault("execution", {})
        lease = execution.get("lease")
        if lease and (timestamp(lease.get("expires_at")) or datetime.min.replace(tzinfo=timezone.utc)) <= at:
            execution.pop("lease", None); changed = True; lease = None
        if lease or execution.get("parked") or status in ("blocked", "rejected", "payout"):
            continue
        fingerprint = source_fingerprint(item)
        due = timestamp(execution.get("next_due_at"))
        cooldown = timestamp(execution.get("cooldown_until"))
        fingerprint_changed = bool(execution.get("completed_fingerprint") and execution.get("completed_fingerprint") != fingerprint)
        explicitly_due = bool(due and due <= at)
        if cooldown and cooldown > at and not fingerprint_changed:
            continue
        selected = None
        if status in accepted_actions and item.get("verified") and (status == "qualified" or money(item.get("accepted_payout")) > 0):
            if not item.get("open", True) and status == "qualified":
                continue
            role, action = accepted_actions[status]
            kind = "application" if status == "qualified" else "accepted-work"
            selected = (_job(item, kind, role, action, 300 if kind == "accepted-work" else 250), item)
        elif status == "submitted":
            action = "Check the official source for feedback or payout status; record the result."
            selected = (_job(item, "submitted-check", "Collector", action, 200), item)
        elif status == "lead" and item.get("open", True):
            action = "Verify source ownership, open status, eligibility, fixed payout, scope, and submission rules."
            selected = (_job(item, "verify", "Verifier", action, 100), item)
        if not selected:
            continue
        kind = selected[0]["kind"]
        if (execution.get("completed_fingerprint") == fingerprint and execution.get("completed_kind") == kind
                and execution.get("completed_status") == status
                and not explicitly_due):
            continue
        if kind in ("accepted-work", "application"):
            accepted.append(selected)
        elif kind == "submitted-check":
            followups.append(selected)
        else:
            verifications.append(selected)

    def sort_key(pair: tuple[dict, dict]) -> tuple:
        job, item = pair
        return (-job["priority"], -money(item.get("accepted_payout")), -money(item.get("advertised_payout")), -float(item.get("score", 0)), job["id"])

    accepted.sort(key=sort_key); followups.sort(key=sort_key); verifications.sort(key=sort_key)
    chosen = accepted[:max_jobs]
    remaining = max_jobs - len(chosen)
    # Cap recurring checks at two so unchanged submissions cannot permanently
    # starve new verification work from a five-slot queue.
    chosen += followups[:min(2, remaining)]
    remaining = max_jobs - len(chosen)
    chosen += verifications[:remaining]
    remaining = max_jobs - len(chosen)
    if remaining:
        chosen += followups[2:2 + remaining]
    jobs = [pair[0] for pair in chosen[:max_jobs]]
    queue = {
        "version": 1, "generated_at": iso(at), "max_jobs": max_jobs, "jobs": jobs,
        "counts": {"queued": len(jobs), "accepted_work": sum(j["kind"] in ("accepted-work", "application") for j in jobs),
                   "submitted_checks": sum(j["kind"] == "submitted-check" for j in jobs),
                   "verifications": sum(j["kind"] == "verify" for j in jobs),
                   "leased": sum(bool(x.get("execution", {}).get("lease")) for x in state.get("items", [])),
                   "parked": sum(bool(x.get("execution", {}).get("parked")) for x in state.get("items", []))},
    }
    return queue, changed


def write_queue(state: dict, path: Path = QUEUE, at: datetime | None = None) -> dict:
    queue, changed = build_queue(state, at)
    if changed:
        atomic_json(path.parent / "state.json", state)
    atomic_json(path, queue)
    return queue


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
        if row.get("enabled", True):
            sources.append((row["name"], row["url"], lambda payload, name, rules=row: parse_rss(payload, name, rules)))
    track_priority = {"submitted": 5, "review": 4, "working": 3, "claimed": 2, "qualified": 1, "lead": 0}
    trackable = sorted(state.get("items", []), key=lambda x: (track_priority.get(x.get("status", "lead"), -1), money(x.get("accepted_payout"))), reverse=True)
    for row in trackable:
        match = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+)/issues/(\d+)", row.get("url", ""))
        if match and row.get("status", "lead") not in ("blocked", "payout", "rejected"):
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
    queue, _ = build_queue(state)
    atomic_json(state_path, state)
    atomic_json(state_path.parent / "queue.json", queue)
    write_dashboard(state, state_path.parent / "dashboard.md", queue)
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


def _save_operational(state: dict, state_path: Path, queue_path: Path, at: datetime) -> dict:
    queue, _ = build_queue(state, at)
    atomic_json(state_path, state)
    atomic_json(queue_path, queue)
    write_dashboard(state, state_path.parent / "dashboard.md", queue)
    return queue


def claim_job(job: str, owner: str, lease_minutes: int = 60, state_path: Path = STATE,
              queue_path: Path = QUEUE, at: datetime | None = None) -> dict:
    at = (at or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    if not clean(owner, 80):
        raise ValueError("owner is required")
    if not 5 <= lease_minutes <= 1440:
        raise ValueError("lease minutes must be between 5 and 1440")
    state = load(state_path, {"items": []})
    queue, _ = build_queue(state, at)
    queued = next((row for row in queue["jobs"] if row["id"] == job), None)
    if not queued:
        raise RuntimeError("job is not currently claimable")
    item = next((row for row in state.get("items", []) if row.get("id") == queued["item_id"]), None)
    if not item or source_fingerprint(item) != queued["source_fingerprint"]:
        raise RuntimeError("job source changed; regenerate the queue before claiming")
    lease = {"owner": clean(owner, 80), "claimed_at": iso(at), "expires_at": iso(at + timedelta(minutes=lease_minutes))}
    execution = item.setdefault("execution", {})
    execution["lease"] = lease
    execution["current_job"] = {key: queued[key] for key in ("id", "kind", "source_fingerprint")}
    _save_operational(state, state_path, queue_path, at)
    return {**queued, "lease": lease}


def record_job(job: str, outcome: str, owner: str = "", note: str = "", checkpoint: str = "",
               next_due_at: str = "", cooldown_hours: float | None = None, state_path: Path = STATE,
               queue_path: Path = QUEUE, at: datetime | None = None) -> dict:
    allowed = {"done", "checkpoint", "failed", "verification-failed", "rejected"}
    if outcome not in allowed:
        raise ValueError(f"outcome must be one of: {', '.join(sorted(allowed))}")
    at = (at or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    state = load(state_path, {"items": []})
    item = next((row for row in state.get("items", []) if row.get("execution", {}).get("current_job", {}).get("id") == job), None)
    if not item:
        raise RuntimeError("job has no recorded lease")
    execution = item.setdefault("execution", {})
    lease, current = execution.get("lease", {}), execution.get("current_job", {})
    if not lease or not timestamp(lease.get("expires_at")) or timestamp(lease.get("expires_at")) <= at:
        execution.pop("lease", None)
        _save_operational(state, state_path, queue_path, at)
        raise RuntimeError("job lease expired")
    if owner and clean(owner, 80) != lease.get("owner"):
        raise RuntimeError("job is leased to another owner")
    if source_fingerprint(item) != current.get("source_fingerprint"):
        execution.pop("lease", None)
        execution.pop("current_job", None)
        _save_operational(state, state_path, queue_path, at)
        raise RuntimeError("job source changed after claim; lease released without recording an outcome")
    due = timestamp(next_due_at)
    if next_due_at and not due:
        raise ValueError("next due time must be ISO-8601")
    if cooldown_hours is not None and not 0 <= cooldown_hours <= 24 * 365:
        raise ValueError("cooldown hours must be between 0 and 8760")
    execution.update({"last_outcome": outcome, "last_outcome_at": iso(at), "last_note": clean(note, 500)})
    if checkpoint:
        execution["checkpoint"] = {"at": iso(at), "summary": clean(checkpoint, 500)}
    if not due and current.get("kind") == "submitted-check" and outcome == "done":
        due = at + timedelta(hours=DEFAULT_COOLDOWN_HOURS if cooldown_hours is None else cooldown_hours)
    if due:
        execution["next_due_at"] = iso(due)
    else:
        execution.pop("next_due_at", None)
    default_cooldown = DEFAULT_COOLDOWN_HOURS if current.get("kind") == "submitted-check" or outcome in ("checkpoint", "failed") else 0
    hours = default_cooldown if cooldown_hours is None else cooldown_hours
    if hours:
        execution["cooldown_until"] = iso(at + timedelta(hours=hours))
    else:
        execution.pop("cooldown_until", None)
    if outcome == "done":
        execution["completed_fingerprint"] = current["source_fingerprint"]
        execution["completed_kind"] = current["kind"]
        execution["completed_status"] = item.get("status", "lead")
    elif outcome in ("verification-failed", "rejected"):
        execution["parked"] = True
        execution["parked_reason"] = outcome
        if outcome == "rejected":
            item["status"] = "rejected"
    execution["last_job"] = current
    execution.pop("lease", None); execution.pop("current_job", None)
    queue = _save_operational(state, state_path, queue_path, at)
    return {"job_id": job, "item_id": item["id"], "outcome": outcome, "queue_size": len(queue["jobs"])}


def write_dashboard(state: dict, path: Path = DASHBOARD, queue: dict | None = None) -> None:
    items = state.get("items", [])
    advertised = sum(money(x.get("advertised_payout")) for x in items if x.get("status") != "rejected" and x.get("open", True))
    accepted = sum(money(x.get("accepted_payout")) for x in items)
    collected = sum(money(x.get("collected")) for x in items)
    spend = sum(money(x.get("spend")) for x in items)
    pending = sum(max(0, money(x.get("accepted_payout")) - money(x.get("collected"))) for x in items)
    active = sum(money(x.get("accepted_payout")) for x in items if x.get("status") in ("claimed", "working", "review", "blocked", "submitted"))
    claims = sum(x.get("status") in ("claimed", "working", "review", "submitted") or (x.get("status") == "blocked" and x.get("application_submitted", False)) for x in items)
    counts = {status: sum(x.get("status") == status for x in items) for status in STATUS_LABELS}
    queue = queue or load(path.parent / "queue.json", {"jobs": [], "counts": {}})
    qcounts, jobs = queue.get("counts", {}), queue.get("jobs", [])
    next_work = (f"{jobs[0].get('role')}: {jobs[0].get('safe_next_action')} [{jobs[0].get('source_url')}]" if jobs else "No claimable queued work.")
    lines = ["# Cash Ops Control", "", f"Updated: {state.get('last_scan', 'never')}  ", f"Scan health: **{state.get('scan_health', 'not run')}**", "", "## Execution queue", "",
             f"Queued: **{len(jobs)}/{queue.get('max_jobs', MAX_QUEUE_JOBS)}** · Leased: **{qcounts.get('leased', 0)}** · Parked: **{qcounts.get('parked', 0)}**  ",
             f"Accepted/application: **{qcounts.get('accepted_work', 0)}** · Submitted checks: **{qcounts.get('submitted_checks', 0)}** · Verifications: **{qcounts.get('verifications', 0)}**  ",
             f"Next queued work: {next_work}", "", "## Financial ledger", "",
             "| Measure | USD | Meaning |", "|---|---:|---|", f"| Advertised | ${advertised:,.2f} | Public fixed amounts observed; not earned |",
             f"| Accepted | ${accepted:,.2f} | Operator-recorded agreed payouts; not yet cash |", f"| Collected | ${collected:,.2f} | Operator-recorded money received |",
             f"| Pending payout | ${pending:,.2f} | Accepted less recorded collection, floored per item |", f"| Active paid work | ${active:,.2f} | Accepted value in active work stages |",
             f"| Spend | ${spend:,.2f} | Operator-recorded costs |", f"| Net | ${collected - spend:,.2f} | Recorded collection less recorded spend |",
             "", f"Applications/claims in progress: **{claims}**  ", f"Best next action: {next_work}  ",
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
    markers, by_number = {}, {}
    for issue in tracked if isinstance(tracked, list) else []:
        by_number[issue["number"]] = issue
        found = re.search(r"<!-- cash-ops:([a-f0-9]{20}) -->", issue.get("body") or "")
        if found: markers[found.group(1)] = issue
    eligible = [row for row in state.get("items", []) if row.get("status", "lead") not in ("payout", "rejected") and (row.get("verified") or row.get("status") != "lead")]
    for row in sorted(eligible, key=lambda x: (x.get("score", 0), money(x.get("advertised_payout"))), reverse=True)[:5]:
        status = row.get("status", "lead") if row.get("status") in STATUS_LABELS else "lead"
        body = f"<!-- cash-ops:{row['id']} -->\nPublic source: {row['url']}\n\nAdvertised payout: {row.get('advertised_payout')} USD\nVerification: {'operator verified' if row.get('verified') else 'required before outreach or claim'}\nScore: {row.get('score', 0)}/100\n"
        data = {"title": f"[Cash Ops] {clean(row.get('title'), 180)}", "body": body, "labels": [status]}
        existing = by_number.get(row.get("tracker_issue_number")) or markers.get(row["id"])
        number = existing.get("number") if existing else row.get("tracker_issue_number")
        current_labels = sorted(x.get("name") for x in existing.get("labels", [])) if existing else []
        unchanged = existing and existing.get("title") == data["title"] and existing.get("body") == data["body"] and current_labels == sorted(data["labels"])
        result = existing if unchanged else api(repo, f"/issues/{number}" if number else "/issues", "PATCH" if number else "POST", data, token)
        if not number:
            row["tracker_issue_number"] = result["number"]
            atomic_json(state_path, state)
        elif not row.get("tracker_issue_number"):
            row["tracker_issue_number"] = number
            atomic_json(state_path, state)
    atomic_json(state_path, state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("scan"); sub.add_parser("report"); sub.add_parser("sync-issues")
    claim = sub.add_parser("claim", help="claim one queued job with an expiring lease")
    claim.add_argument("job_id"); claim.add_argument("--owner", required=True); claim.add_argument("--lease-minutes", type=int, default=60)
    record = sub.add_parser("record", help="record a leased job outcome and optional checkpoint")
    record.add_argument("job_id"); record.add_argument("--outcome", required=True,
                        choices=("done", "checkpoint", "failed", "verification-failed", "rejected"))
    record.add_argument("--owner", default=""); record.add_argument("--note", default="")
    record.add_argument("--checkpoint", default=""); record.add_argument("--next-due-at", default="")
    record.add_argument("--cooldown-hours", type=float)
    args = parser.parse_args()
    try:
        if args.command in (None, "scan"): scan()
        elif args.command == "report":
            state = load(STATE, {}); queue = write_queue(state); write_dashboard(state, DASHBOARD, queue)
        elif args.command == "sync-issues": sync_issues()
        elif args.command == "claim": print(json.dumps(claim_job(args.job_id, args.owner, args.lease_minutes), sort_keys=True))
        else:
            print(json.dumps(record_job(args.job_id, args.outcome, args.owner, args.note, args.checkpoint,
                                        args.next_due_at, args.cooldown_hours), sort_keys=True))
        return 0
    except Exception as exc:
        print(f"cash-ops-control: {exc}", file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
