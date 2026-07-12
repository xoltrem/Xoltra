# Reference Stubs — NOT wired into the running app

Everything in this folder is unconnected reference/scaffold code pulled in
from a separate design bundle. None of it is imported by `frontend/` or
`backend/`, and none of these routes are live.

## What's here

- `lib/` — stub helpers for an alternate Next.js-API-routes auth/memory
  design: JWT issue/verify (`tokens.js`), a rate limiter using
  `@vercel/kv` (`rateLimit.js`), an auth middleware wrapper (`withAuth.js`),
  a stubbed DB client (`db.js`), and stub memory/skill-XP engines
  (`memoryEngine.js`, `skillEngine.js`).
- `pages/api/auth/login.js`, `pages/api/auth/refresh.js`,
  `pages/api/memory/index.js` — example Next.js API route handlers built on
  top of the `lib/` stubs above (relative imports assume this exact
  `pages/api/<x>/<y>.js` depth).
- `ApiClient.js` — a plain-JS client stub for calling the above.
- `dataRoute.js` — a separate Express-route stub (zod validation +
  rate limiting) for a "golden record" GET endpoint, unrelated to the
  Next.js stubs above.

## Why it's kept separate

The actual working auth/memory/rate-limiting system for this project is:
- **Auth**: `backend/auth.py` (email+password, JWT) +
  `backend/auth-service/` (Google OAuth + OTP + Turnstile)
- **Rate limiting**: `backend/rate_limit.py` (Flask) +
  `backend/auth-service/auth.js` (Node)
- **Memory**: `backend/knowledge_db.py` + `backend/memory_router.py`

Those are real, tested, and live. This folder is a design reference only —
useful if you want to compare approaches or lift a specific idea (e.g. the
`@vercel/kv` rate-limit pattern), but don't import from it directly without
adapting it to the real backend's data model and auth scheme first.
