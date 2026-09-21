# Cash Ops Control

Cash Ops Control is a deterministic Python 3.11+ intake and ledger for public, explicitly configured bounty sources. It discovers leads; it does not contact anyone, accept work, submit claims, execute source text, or prove income. An operator must verify scope, eligibility, payout terms, and identity from authoritative evidence before moving an item from `lead` to `qualified` or performing outreach. That operator may be an AI following the configured policy; human action is reserved for login, spending, identity, contracts, and other material decisions.

The eight role names are logical stages, not resident agents or autonomous Astra sessions: Scout (`lead`), Verifier (`qualified`), Claimant (`claimed`), Builder (`working`), Reviewer (`review`), Submitter (`submitted`), Collector (`payout`), and Closer (`rejected`). `blocked` is a pause label usable from any stage.

## Run locally

No package install, LLM API, paid action, database, or service is required.

```bash
cd cash-ops-control
python -m unittest discover -s tests -v
python cash_ops.py scan
python cash_ops.py report
```

Edit `sources.json` to change the narrow GitHub public issue queries. The initial queries only look for public issues referencing Algora or Opire. Add explicit RSS/Atom feeds like this:

```json
"rss": [{"name": "Maintainer bounty feed", "url": "https://example.org/bounties.xml", "enabled": true}]
```

Each request has a configured timeout, a 5 MB response cap, conditional ETag/Last-Modified caching, and a descriptive user agent. Auth is sent only to the exact GitHub API host, and authenticated cross-origin redirects are refused. URLs are canonicalized and deduplicated. The scanner retains old leads when a source is unavailable, refreshes up to ten tracked active GitHub issues, and records observations, errors, and scan health in both `state.json` and `dashboard.md`.

## Review and ledger rules

Automatic discoveries always start as `lead`, even when a fixed USD amount appears beside “bounty,” “reward,” or “payout.” Ranges, pools, “from,” and “up to” amounts are not treated as fixed. An operator may edit these durable fields in `state.json`; scans preserve them: `status`, `verified`, `accepted_payout`, `collected`, `spend`, `notes`, `owner`, and `tracker_issue_number`. Older `human_verified` values migrate to `verified` during a scan.

Set `verified` to `true` only after checking authoritative public evidence, then change `status` as work progresses. `advertised_payout` means a fixed amount observed in public text. `accepted_payout` means an operator recorded an agreement. `collected` means an operator recorded received funds. The dashboard sums them separately and never reports leads as earnings. ChatGPT Work quota and cost remain unknown because no supported local quota interface is available.

Keep this repository public-safe: store only public source references and operational fields. Do not paste private Gmail messages, client content, credentials, tax details, or private discussion bodies into the state, config, dashboard, or issues.

## GitHub Actions and optional tracker issues

`.github/workflows/cash-ops.yml` runs tests and scans at minute 17 every six hours, on manual dispatch, and on relevant pushes. It uses GitHub-hosted standard actions and `GITHUB_TOKEN`; it invokes no LLM. Concurrency prevents overlapping scans, and the publish step rebases the latest branch before pushing state.

Issue sync is disabled by default. To enable it, set `issue_repo` in `sources.json` to the current repository’s exact `owner/name`. The command refuses a different repository when Actions provides `GITHUB_REPOSITORY`. It creates/updates at most five highest-scored verified or active tracker issues using only `GITHUB_TOKEN` and applies one of: `lead`, `qualified`, `claimed`, `working`, `review`, `blocked`, `submitted`, `payout`, or `rejected`. Stable body markers recover existing trackers, and each new issue number is written atomically before continuing.

For a Windows PC, run the setup script in a regular PowerShell session:

```powershell
cd path\to\cash-ops-control
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows-task.ps1
```

The task runs `python cash_ops.py scan` every six hours when the PC is available, starts missed runs when possible, does not wake the PC, and stops after ten minutes. It uses the Python executable visible during setup.

## Limits

Public search can miss bounties, APIs can throttle or change, text extraction can misread amounts, and a displayed bounty may be stale, unavailable, restricted, or unpaid. ETags reduce repeat downloads but do not guarantee freshness. The program does not assess legal/tax obligations, platform terms, eligibility, technical fit, acceptance, collection, or profit. Operator verification remains mandatory before outreach or claims.
