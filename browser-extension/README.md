# Xoltra Companion Extension

Chrome side-panel companion for Xoltra: launch and inspect workflows from any
page, capture page context into runs, apply session-only parameter overrides,
and chat with the workflow assistant.

Full design rationale: `docs/Xoltra_Companion_Extension_Spec.md` (repo root).

## Build & install

```bash
cd browser-extension
npm install
npm run build        # -> dist/
```

Then in Chrome (≥120): `chrome://extensions` → enable Developer mode →
**Load unpacked** → select `browser-extension/dist`.

`npm run watch` rebuilds on change (click ↻ on the extension card to reload).
`npm run typecheck` runs strict TypeScript with no emit.

## First run

1. Start the backend (`backend/app.py`, port 5001).
2. Click the extension icon (or Alt+X) → "Open sign-in" → email + password.
   Terms of Service must already be accepted in the web app.
3. Capture a page (panel button, right-click menu, or Alt+Shift+X) and run a
   workflow — the capture rides in as `trigger_data.page_context`.

## Surfaces

| Surface | File | Notes |
|---|---|---|
| Side panel | `src/sidepanel/` | Workflows / Runs / Assistant tabs, Ctrl+K palette |
| Options | `src/options/` | sign-in, backend URLs (custom origins prompt for permission) |
| Service worker | `src/background/` | capture orchestration, context menus; stateless |
| Content capture | `src/content/capture.ts` | injected on demand; never reads form values |

## Design constraints worth knowing

- **Session overrides** live in `chrome.storage.session` — they die with the
  browser session by construction and are sent per-run as `param_overrides`
  (never persisted server-side).
- **No auto-retry on 4xx** and assistant sends are ≥3s apart: the backend
  escalates repeated 429s into account timeouts.
- JWT expires after 24h (no refresh token) — a 401 anywhere routes back to
  the options sign-in.
- Manual test matrix: sign-in → capture on a normal page → run with an
  override → verify in Runs tab; capture on `chrome://` must fail with a
  visible message; Ctrl+K palette fully keyboard-navigable.
