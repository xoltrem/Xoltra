# Deployment guide

## Set up three Vercel projects (not one)

The frontend already assumes this — `src/lib/api.ts` reads backend URLs
from `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_API_URL_FALLBACK` env vars rather
than hardcoding ports, specifically so it works "unchanged across... any
cloud deploy (Vercel etc — no custom ports, just HTTPS domains)" per its
own header comment.

| Vercel project | Root Directory | Framework preset | Env vars |
|---|---|---|---|
| `xoltra-frontend` | `frontend` | Next.js (auto-detected) | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_API_URL_FALLBACK` |
| `xoltra-secure-api` | `backend/secure-api` | Other | `MASTER_KEY`, `CLIENT_ONE`, `CLIENT_TWO`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `NODE_ENV=production` |
| `xoltra-auth-service` | `backend/auth-service` | Other | `FRONTEND_URL`, `GOOGLE_CLIENT_ID`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURE`, `SMTP_USER`, `SMTP_PASS`, `OTP_EMAIL_FROM`, `TURNSTILE_SECRET_KEY`, `NODE_ENV=production` |

In Vercel: **New Project → Import repo → Root Directory → (path from table
above)**. Do this three times, once per row. `backend/secure-api/vercel.json`
and `backend/auth-service/vercel.json` each contain a `rewrites` rule so
their single Express file handles every route; `frontend/` needs no
`vercel.json` at all, Next.js is auto-detected.

`services/agent-engine-python/` and `clients/unity/` are not part of this
web deploy — see "Not deployed to Vercel" below.

---

## What was broken, and what I changed

### 1. `vercel.json` pointed at files that don't exist (the actual blocker)
Original config:
```json
"builds": [
  { "src": "backend/secure-api/server.js", "use": "@vercel/node" },
  { "src": "backend/auth-service/auth-server.js", "use": "@vercel/node" }
]
```
There was no `backend/` directory anywhere — `server.js` and
`auth-server.js` sat at repo root. Build failed before touching app code.
**Fix**: moved the files to real `backend/secure-api/` and
`backend/auth-service/` directories, and gave each its own minimal
`vercel.json` using `rewrites` instead of the legacy `builds`/`routes`
schema.

### 2. The legacy `builds` array disabled Next.js framework detection
Even with correct paths, having a `builds` array in `vercel.json` stops
Vercel from ever running `next build` — your frontend would still never
deploy. **Fix**: split into three independent Vercel projects (table
above) so the frontend gets normal zero-config Next.js detection, and each
backend gets its own tiny `rewrites`-based config.

### 3. No `app/` or `pages/` directory existed
Every `.tsx` file was flat at repo root; `tsconfig.json` maps `@/*` →
`./src/*`, but `src/` only contained two unrelated Python files. `next
build` would fail immediately with "Couldn't find any pages or app
directory." **Fix**: rebuilt `frontend/src/app/` (App Router) and
`frontend/src/components/`, `lib/`, `stores/` to match every `@/...` import
already present in the code — nothing was rewritten, just moved to where
the code already expected it to be. Also added `frontend/src/app/page.tsx`
(redirects to `/workflows`) since no route previously answered `"/"`.

| File found at root | Moved to |
|---|---|
| `layout.tsx` | `frontend/src/app/layout.tsx` |
| `globals.css` | `frontend/src/app/globals.css` |
| `page.tsx` (identical to `WorkflowsPage.tsx`) | `frontend/src/app/workflows/page.tsx` |
| `KnowledgePage.tsx` | `frontend/src/app/knowledge/page.tsx` |
| `ToolsPage.tsx` | `frontend/src/app/tools/page.tsx` |
| `SettingsPage.tsx` | `frontend/src/app/settings/page.tsx` |
| `Button.tsx` | `frontend/src/components/ui/Button.tsx` |
| `CommandPalette.tsx` | `frontend/src/components/ui/CommandPalette.tsx` |
| `Sidebar.tsx`, `Topbar.tsx` | `frontend/src/components/layout/` |
| `AIAssistantPanel.tsx`, `CustomNode.tsx` | `frontend/src/components/workflow/` |
| `PersonalizationPanel.tsx` | `frontend/src/components/settings/` |
| `RoleSelector.tsx` | `frontend/src/components/roles/` (not imported anywhere else in the codebase — check whether it's still needed) |
| `utils.ts`, `api.ts`, `xoltra-ai.js` | `frontend/src/lib/` |
| `index.ts` (zustand store) | `frontend/src/stores/index.ts` |

### 4. Duplicate case-variant component files
`Button.tsx`/`button.tsx`, `Sidebar.tsx`/`sidebar.tsx`, `Topbar.tsx`/`topbar.tsx`,
`CommandPalette.tsx`/`commandpalette.tsx`, `CustomNode.tsx`/`customnode.tsx`
were byte-for-byte identical pairs — pure flattening debris, not merge
conflicts. **Fix**: kept one canonical (capitalized, matching the actual
`@/components/...` import paths) copy of each, dropped the lowercase twin.

### 5. `Node/` folder was a stale duplicate of root files
`Node/permission_bridge.py`, `Node/schemas.json`, `Node/architecture.md`
were byte-identical to the root copies. **Fix**: dropped, kept one copy
each under `services/agent-engine-python/` (Python files) or `docs/`
(schemas/architecture).

### 6. `mnt/user-data/outputs/...` was accidental scratch output
Looked like leftover output from a prior agent session, zipped in by
mistake (`mnt/user-data/outputs/secure-api/vercel.json`,
`.../auth-pipeline/backend/Auth_server.js`). Not part of the project.
**Fix**: dropped. (Its `vercel.json` — a `rewrites`-based single-file
config — is actually what the corrected `backend/secure-api/vercel.json`
now looks like, for what it's worth.)

### 7. Missing `helmet` dependency
`backend/secure-api/server.js` does `require('helmet')`, but `helmet` was
never listed in any `package.json` in the repo — first deploy would crash
with `MODULE_NOT_FOUND` the moment that line executed. **Fix**: added
`helmet` to `backend/secure-api/package.json`.

### 8. Replay-nonce and rate-limit state were per-process `Map()`s
```js
const seenNonces = new Map();   // replay protection
const buckets = new Map();      // rate limiting
```
On Vercel, requests land on whatever lambda instance is warm — there's no
guarantee two requests from the same attacker hit the same process. A
replayed request that lands on a different cold instance would sail
through, and the rate limiter resets per-instance instead of globally. The
file's own docstring advertises "replayed nonces are rejected on second
use," which was only true in a single long-running local process.
**Fix**: both now use the Upstash Redis client (`kv`) that was already a
dependency and already initialized in the file — nonce claims use an
atomic `SET NX EX` (`services/`-style claim-once-across-instances), rate
limiting uses `INCR` + `EXPIRE` on a per-minute bucket key. No new
dependency, no behavior change from the caller's perspective, just made
correct across serverless instances.

### 9. Not deployed to Vercel (left in place, organized, out of the way)
- `services/agent-engine-python/` — Python workflow/simulation/knowledge
  backend (FastAPI-style, `main.py`, `workflow_engine.py`, etc.). This is a
  long-running Python service, not a serverless function; it needs its own
  host (Railway, Render, Fly, a VM) — it was never going to deploy via this
  `vercel.json` regardless of the other fixes.
- `clients/unity/` — C# Unity simulation client. Not a web deploy target.
- `automation-agent/` — kept separate per its own README (it has its own
  Vite dashboard with a separate `package.json`, deliberately not merged
  into `frontend/`). Also recovered `Login.jsx` + its own `main.jsx` /
  `index.html` / `vite.config.js` into `automation-agent/auth-frontend/` —
  these were sitting loose at repo root. Note: `automation-agent/README.md`
  says `Login.jsx` "belongs to this dashboard," but the code itself calls
  `localhost:5000`, which is `auth-server.js`'s port, not the agent's
  (`:4000`) — I placed it as its own small `auth-frontend/` mini-app
  matching what the code actually talks to. Worth a second look from
  whoever owns that doc.

## Environment variables reference
See the table at the top of this file. `scan.js` (the project's own
audit skill) also flagged three `eval()` injection-risk findings in
`services/agent-engine-python/permission_bridge.py` and `scan.js` itself —
unrelated to the deploy failure, not fixed here, worth a follow-up pass.
