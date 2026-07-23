# Project Auditor Skill

Use this skill to verify a project end-to-end and produce a machine-readable
report another AI can act on directly — no human translation needed.

## When to trigger
- User asks to "check", "test", "audit", "verify", or "debug" the project.
- Before marking any task/feature as complete.
- After generating or editing server/API code.

## What it does
1. Walks the entire project tree (skips node_modules/.git/build/venv).
2. Static-scans every source file for: hardcoded secrets/keys, empty/bare
   exception handlers, sensitive data in logs, `eval()`/shell-exec injection
   risk, unfinished TODO/FIXME markers.
3. If a server is reachable, simulates a real client:
   - hits `/health`
   - if the secure-api signed/encrypted protocol is detected (`x-signature`
     header pattern found in source), verifies: unsigned requests are
     rejected (401), signature validation is active, and replayed
     nonces are rejected on second use.
4. Writes `audit-report.json` to the project root and prints a
   `BLOCKING_ISSUES` list to stdout for anything `critical` or `high`.

## How to run
```bash
node scan.js /path/to/project --base-url=http://localhost:8443
# with full security-layer round trip (needs a real client secret, not MASTER_KEY):
node scan.js /path/to/project --base-url=http://localhost:8443 --key-id=client1 --secret=<hex>
```
No install step, no dependencies — Node built-ins only.

## How to interpret `audit-report.json`
```json
{
  "totals": { "critical": 0, "high": 1, "medium": 2, "low": 3, "pass": 5, "info": 2 },
  "findings": [
    {
      "id": 7, "severity": "high", "category": "hardcoded_secret",
      "message": "possible hardcoded secret literal",
      "file": "node/server.js", "line": 42,
      "snippet": "const apiKey = \"sk_live_...\""
    }
  ]
}
```
Each finding has everything needed to fix without re-reading the whole repo:
`file`, `line`, `snippet`/`location_hint`, `category`, and a plain-language
`message`. Treat the run as failed if `process.exitCode === 1`
(equivalently: any `critical` or `high` finding exists).

## Agent workflow
1. Run `scan.js` against the project.
2. If `BLOCKING_ISSUES` is non-empty: open each `file:line`, fix per
   `message`/`category`, re-run scan.js.
3. Repeat until `NO_BLOCKING_ISSUES`.
4. Only then report the task complete to the user.
