# n8n repository API health — independent proof of work

A small credential-free n8n workflow: Manual Trigger → public GitHub API request → validated JSON report.

## Honest status
Created with AI assistance as an independent demonstration. It is **not a client production workflow**, has not been run end-to-end inside an n8n instance, and is not represented as historical client experience. The Code node is exercised directly by the included Node.js test harness. Import/schema compatibility and HTTP-node behavior still need validation in the target n8n version.

For an actually running automation in this repository, see [Cash Ops Control](../../cash-ops-control/README.md) and its [verified external run](https://github.com/apb31/maintainerops/actions/runs/35652225004). That system uses Python and GitHub Actions, **not n8n**.

## What it demonstrates
- Fixed HTTPS endpoint, GET only, no credentials or private data.
- 15-second HTTP timeout; at most three attempts for request failures.
- Non-200 HTTP responses produce an explicit failure record, never a success report. HTTP 429 and 5xx are marked retryable; this sample does not automatically retry status-code failures.
- Repository identity and non-negative integer counters are checked before emitting a report.
- Distinguishes GitHub's combined issue/PR count from an issues-only count.
- No email, paid model calls, automatic schedules, arbitrary URLs or downstream writes.

## Reproduce
Import `workflow.json` into n8n; inspect the three nodes, then execute manually. No activation is required. The host needs access to api.github.com. Stop and inspect a red/error result; do not label it a successful run.

Run local logic/structure checks with:
```bash
node proofs/n8n-repo-health/test-workflow.cjs
```

Checks validate the actual embedded Code-node program using fixed fixtures; they do not substitute for n8n runtime testing.

References: [HTTP Request](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/), [Code](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.code/).
