# Xoltra

## Structure

```
Xoltra/
├── frontend/              Next.js app — ONE package.json
├── backend/                Flask (app.py, requirements.txt) — ONE package.json
│   ├── secure-api/          Node: encrypted KV store (currently unused by the app)
│   ├── auth-service/        Node: Google OAuth + OTP, hands off to Flask for a real JWT
│   └── permission_bridge/    renamed from "Node/" — it's Python, not Node.js
├── automation-agent/       Separate bolt-on tool (own agent + own Vite dashboard)
│                            Kept outside frontend/backend — different build tooling
│                            (Vite vs Next.js) means it can't share a package.json.
└── vercel.json
```

## Auth flow (Google OAuth <-> Flask)

1. User signs in with Google + OTP via backend/auth-service/auth.js
2. On success, auth.js calls Flask's POST /api/auth/oauth-issue (backend/auth.py)
3. Flask finds-or-creates the user and returns a normal Flask JWT
4. That JWT works with every existing @require_auth route — nothing else changes

## Known issue, not yet resolved

backend/secure-api is not called by anything in the live app (confirmed by
grep across the whole codebase). Kept, not deleted — see its own README.
