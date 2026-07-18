# Changed files only — ToS moderation/timeout system

Diffed against Xoltra-main (original). 8 modified, 2 new.

## New
- backend/moderation.py — escalating timeout ladder, record_violation(), rate_limit_user()
- frontend/src/components/ui/SuspendedAccountModal.tsx — global 403-suspension screen

## Modified
- backend/app.py — require_auth now checks active timeouts
- backend/auth.py — wired to moderation checks
- backend/admin_routes.py — admin timeout list/set/clear endpoints
- backend/rate_limit.py — added per-user limiter alongside per-IP
- backend/.env.example — new moderation-related env vars
- frontend/src/lib/api.ts — moderation/timeout API calls
- frontend/src/app/layout.tsx — mounts SuspendedAccountModal globally
- frontend/src/components/settings/AdminPanel.tsx — admin moderation controls

Drop these into the corresponding paths of your working tree (same relative
structure as the full repo) to apply on top of Xoltra-main.
