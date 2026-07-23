# Deployment guide

> **Accuracy note (added during a later pass, not part of the original doc):**
> Two things below no longer match this repo checkout, verified directly
> rather than assumed:
> 1. `backend/secure-api/vercel.json` and `backend/auth-service/vercel.json`
>    are referenced below as already existing — they don't. Neither
>    `backend/secure-api/` nor `backend/auth-service/` currently has a
>    `vercel.json` or its own `package.json`. The "three Vercel projects"
>    plan is directionally still right (the Root Directory paths in the
>    table are correct), but none of the three are actually deployable from
>    this checkout as-is without adding those files back.
> 2. The "What was broken, and what I changed" section below refers to
>    `services/agent-engine-python/` and `clients/unity/` — neither exists
>    in this repo. The equivalent code now lives at `backend/` (Python) and
>    `unity-client/` (C#). Whatever rename/reorg happened after this section
>    was written was never reflected here. Treat every path in that section
>    as historical, not current.
>
> `backend/secure-api` itself is real, deliberately-built code (signature-
> based auth, Redis-backed replay/rate-limit protection) — not dead code to
> delete, just currently unwired to anything. Whether to finish integrating
> it or formally deprecate it is a product decision, not made here.

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
above)**. Do this three times, once per row. As of this checkout,
`backend/secure-api/` and `backend/auth-service/` each need a `vercel.json`
(a `rewrites` rule pointing every route at the single Express file) and
their own minimal `package.json` added back before this will actually
deploy — see the accuracy note above. `frontend/` needs no `vercel.json` at
all, Next.js is auto-detected.

**Not covered by this doc, and not verified:** where `backend/app.py`
(the Flask app — workflow engine, node library, permission bridge,
subscription/billing) actually runs. It's a long-running process
(SQLite file, in-process audit log, a websocket thread for the Unity
bridge per `unity_bridge.py`), not a serverless function, so it needs a
persistent host (Railway, Render, Fly, a VM) — same constraint the
original version of this doc noted for the Python service, wherever it
currently lives. Confirm current hosting before relying on this doc for
the Flask side.

`automation-agent/` is also not part of this Vercel deploy — see its own
`README.md`. It has its own Vite dashboard with a separate `package.json`,
deliberately not merged into `frontend/`.

---

## What was broken, and what was changed (historical — paths below predate a later reorg, see accuracy note at top)

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
schema. (Those `vercel.json` files are no longer present in this checkout
— see accuracy note.)

### 2. The legacy `builds` array disabled Next.js framework detection
Even with correct paths, having a `builds` array in `vercel.json` stops
Vercel from ever running `next build` — your frontend would still never
deploy. **Fix**: split into three independent Vercel projects (table
above) so the frontend gets normal zero-config Next.js detection, and each
backend gets its own tiny `rewrites`-based config.

### 3. No `app/` or `pages/` directory existed
Every `.tsx` file was flat at repo root; `tsconfig.json` maps `@/*` →
`./src/*`. **Fix**: rebuilt `frontend/src/app/` (App Router) and
`frontend/src/components/`, `lib/`, `stores/` to match every `@/...` import
already present in the code. This part matches the current tree.

### 4. Duplicate case-variant component files
Byte-for-byte identical pairs (`Button.tsx`/`button.tsx`, etc.) were pure
flattening debris. **Fix**: kept one canonical copy of each.

### 5. A stale duplicate Python folder existed at the time
Referred to as `Node/` in the original pass, byte-identical to the
in-use copies. **Fix**: dropped. No `Node/` folder exists in this
checkout, consistent with that cleanup having stuck.

### 6. Accidental scratch output was previously checked in
Leftover output from a prior agent session, zipped in by mistake. **Fix**:
dropped.

### 7. Missing `helmet` dependency
`backend/secure-api/server.js` does `require('helmet')`, but `helmet` was
never listed in any `package.json` in the repo — first deploy would crash
with `MODULE_NOT_FOUND`. **Fix**: added `helmet` to
`backend/secure-api/package.json`. (No `package.json` currently exists in
`backend/secure-api/` in this checkout — re-add before deploying.)

### 8. Replay-nonce and rate-limit state were per-process `Map()`s
```js
const seenNonces = new Map();   // replay protection
const buckets = new Map();      // rate limiting
```
On Vercel, requests land on whatever lambda instance is warm — a replayed
request landing on a different cold instance would sail through, and the
rate limiter reset per-instance instead of globally. **Fix**: both now use
the Upstash Redis client (`kv`) already initialized in the file — nonce
claims use an atomic `SET NX EX`, rate limiting uses `INCR` + `EXPIRE` on a
per-minute bucket key. This fix is present in the current
`backend/secure-api/server.js` — verified directly, still real.

### 9. Services needing their own host (paths below are historical — see accuracy note)
- The Python workflow/simulation/knowledge backend (FastAPI-style,
  `main.py`-equivalent, `workflow_engine.py`, etc.) — a long-running
  process, not a serverless function. Now lives at `backend/` in this
  checkout, not the path originally referenced here.
- The Unity simulation client — not a web deploy target. Now lives at
  `unity-client/` in this checkout.
- `automation-agent/` — kept separate per its own README (own Vite
  dashboard, separate `package.json`, deliberately not merged into
  `frontend/`).

## Environment variables reference
See the table at the top of this file. `scan.js` (the project's own audit
skill) also flagged three `eval()` injection-risk findings — worth a
follow-up pass, not fixed here.
