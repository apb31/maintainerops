# Cash Ops Control

Cash Ops Control is a deterministic Python 3.11+ intake and ledger for public, explicitly configured bounty and buyer-request sources. It discovers leads; it does not contact anyone, accept work, submit claims, execute source text, or prove income. An operator must verify scope, eligibility, payout terms, and identity from authoritative evidence before moving an item from `lead` to `qualified` or performing outreach. That operator may be an AI following the configured policy; human action is reserved for login, spending, identity, contracts, and other material decisions.

The eight role names are logical stages, not resident agents or autonomous Astra sessions: Scout (`lead`), Verifier (`qualified`), Claimant (`claimed`), Builder (`working`), Reviewer (`review`), Submitter (`submitted`), Collector (`payout`), and Closer (`rejected`). `blocked` is a pause label usable from any stage.

## Run locally

No package install, LLM API, paid action, database, or service is required.

```bash
cd cash-ops-control
python -m unittest discover -s tests -v
python cash_ops.py scan
python cash_ops.py report
```

Edit `sources.json` to change the narrow GitHub public issue queries. The GitHub queries look for Algora bounty mentions or Opire references; the configured RSS feeds add recent buyer requests. Add explicit RSS/Atom feeds like this:

```json
"rss": [{"name": "Maintainer bounty feed", "url": "https://example.org/bounties.xml", "enabled": true}]
```

RSS feeds may optionally set `title_buyer_signals`, `title_seller_exclusions`, `max_age_days`, `max_items`, and `summary_max_chars`. Buyer signals require at least one title match, seller exclusions always win, and an age limit rejects entries whose RSS `pubDate` or Atom `published`/`updated` timestamp is missing or too old. Feeds without these keys retain the original accept-all behavior. Discourse post links are collapsed to one canonical topic URL before deduplication. The default n8n and Make community feeds admit recent buyer posts while excluding common “for hire” seller titles; all three use a 14-day age window. WordPress Jobs additionally excludes full-time, sales, and support titles. Each source stores at most eight short public summaries.

Each request has a configured timeout, a 5 MB response cap, conditional ETag/Last-Modified caching, and a descriptive user agent. Auth is sent only to the exact GitHub API host, and authenticated cross-origin redirects are refused. URLs are canonicalized and deduplicated. The scanner retains old leads when a source is unavailable, refreshes up to ten tracked active GitHub issues, and records observations, errors, and scan health in both `state.json` and `dashboard.md`.

## Review and ledger rules

Automatic discoveries always start as `lead`, even when a fixed USD amount appears beside “bounty,” “reward,” or “payout.” Ranges, pools, “from,” and “up to” amounts are not treated as fixed. An operator may edit these durable fields in `state.json`; scans preserve them: `status`, `verified`, `accepted_payout`, `collected`, `spend`, `notes`, `owner`, and `tracker_issue_number`. Older `human_verified` values migrate to `verified` during a scan.

Set `verified` to `true` only after checking authoritative public evidence, then change `status` as work progresses. `advertised_payout` means a fixed amount observed in public text. `accepted_payout` means an operator recorded an agreement. `collected` means an operator recorded received funds. The dashboard sums them separately and never reports leads as earnings. ChatGPT Work quota and cost remain unknown because no supported local quota interface is available.

Keep this repository public-safe: store only public source references and operational fields. Do not paste private Gmail messages, client content, credentials, tax details, or private discussion bodies into the state, config, dashboard, or issues.

## GitHub Actions and optional tracker issues

`.github/workflows/cash-ops.yml` runs tests and scans every 15 minutes (UTC minutes 7, 22, 37 and 52), on manual dispatch, and on relevant pushes. It uses GitHub-hosted standard actions and `GITHUB_TOKEN`; it invokes no LLM. Concurrency prevents overlapping scans, and the publish step rebases the latest branch before pushing state.

Issue sync is enabled here for `apb31/maintainerops`. For another installation, set `issue_repo` in `sources.json` to the current repository’s exact `owner/name`. The command refuses a different repository when Actions provides `GITHUB_REPOSITORY`. It creates/updates at most five highest-scored verified or active tracker issues using only `GITHUB_TOKEN` and applies one of: `lead`, `qualified`, `claimed`, `working`, `review`, `blocked`, `submitted`, `payout`, or `rejected`. Stable body markers recover existing trackers, and each new issue number is written atomically before continuing.

For a Windows PC, run the setup script in a regular PowerShell session:

```powershell
cd path\to\cash-ops-control
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows-task.ps1
```

The task runs `python cash_ops.py scan` every 15 minutes when the PC is available, starts missed runs when possible, does not wake the PC, and stops after ten minutes. It uses the Python executable visible during setup.

## Limits

Public search can miss bounties, APIs can throttle or change, text extraction can misread amounts, and a displayed bounty may be stale, unavailable, restricted, or unpaid. ETags reduce repeat downloads but do not guarantee freshness. The program does not assess legal/tax obligations, platform terms, eligibility, technical fit, acceptance, collection, or profit. Operator verification remains mandatory before outreach or claims.


## Continuous execution handoff

The external scanner regenerates `queue.json` with at most five actionable public jobs. Accepted work comes first, then qualified applications, due submission checks and new verification. Closed issues may still require feedback/payment handling. Blocked/rejected/parked items do not keep requesting attention. Source update times and comment counts wake completed checks on new evidence; scan timestamps alone do not. Unknown funding never becomes an accepted payout automatically.

A separate ChatGPT automation, **Cash Ops — ejecutar cola**, is configured hourly at :05 (America/Santo_Domingo). A second automation handles matching commercial Gmail events. These automations perform authorized reasoning, applications, replies and deliverables; Python itself does not send proposals or operate an LLM. They remain subject to account quotas, connector access and service availability. No external paid inference is configured. GitHub schedules are best effort, so 15 minutes is the requested cadence, not an uptime guarantee.

The hourly executor reads the small queue and dashboard first, exits quietly if nothing is due, and handles one job per run. Its speculative prospecting limit is four new verifications/applications per local day; accepted work and buyer replies take priority independently. Keep the daily counter and email reservations in the private compact state. Suppress routine scan/proposal/claim notices and repeated unchanged blockers; notify only new material acceptance, delivery, payment or indispensable user intervention.

### Claim, act, checkpoint

Use the current repository HEAD and source record. Example commands (replace the job ID with one actually returned by the queue):

```bash
python cash_ops.py report
python cash_ops.py claim JOB_ID --owner hourly-executor --lease-minutes 60
python cash_ops.py record JOB_ID --owner hourly-executor --outcome checkpoint --checkpoint "Public-safe progress and artifact link" --next-due-at 2026-09-22T10:00:00Z --cooldown-hours 0
python cash_ops.py record JOB_ID --owner hourly-executor --outcome done --note "Public-safe evidence URL"
```

**Publish the claim before making an external action.** Local atomic file writes do not provide cross-host locking. Use a single writer or commit state on top of the current GitHub HEAD and update the ref without force. If the ref moved, reread and reconcile; do not proceed with an uncommitted claim or overwrite someone else's state. A connector-based executor may implement the exact same JSON transition without running the CLI. Update `state.json`, `queue.json` and `dashboard.md` together, preserving unrelated records.

A record's `execution.lease` contains `owner`, `claimed_at`, `expires_at`; `execution.current_job` contains `id`, `kind`, `source_fingerprint`. Other durable fields include `last_outcome`, `last_outcome_at`, `last_note`, `checkpoint`, `next_due_at`, `cooldown_until`, `completed_fingerprint`, `completed_kind`, `completed_status` and `parked`. The scanner preserves these operator fields. Expired leases become claimable again; before retrying a send/claim/PR after a crash, reconcile its receipt at the destination. A lease is not a guarantee of exactly-once delivery.

Record `done` after finishing the current stage and update the opportunity's status/verified/financial fields only with evidence. Record `checkpoint` for resumable progress, `failed` for a retryable failure, and `verification-failed` or `rejected` to park an unsuitable opportunity. Store private content and email receipts only in private state. The CLI rejects stale-source results; reconcile material source changes before taking further action.

Submission checks default to a 72-hour cooldown and next due time. Explicit checkpoints can schedule the next action sooner. A changed source can wake review early; it is not permission to send another follow-up sooner than the communication policy allows. No command is taken from issue/feed text: queue actions are fixed instructions selected by local code.
