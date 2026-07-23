# Xoltra Companion Extension — Design & Engineering Spec

> Deliverables 1–15 required by the Master prompt, followed by the innovation
> backlog. Reflects the implementation shipped in `browser-extension/` and the
> matching backend change (`param_overrides` on the run endpoint).

---

## 1. PRD

**Problem.** Xoltra workflows live in one tab; the work they automate lives in
every other tab. Users context-switch to launch anything, and nothing they are
currently looking at can flow into a run.

**Product.** A Chrome side-panel companion that (a) launches and inspects
workflows from any page, (b) captures the current page as structured context
that rides into runs as `trigger_data`, (c) applies **session-only parameter
overrides** to any node without touching the saved workflow, and (d) embeds
the Xoltra assistant with page context woven in.

**Users.** Existing Xoltra account holders (the PRD's non-technical operator
persona included — every surface is plain-language).

**Non-goals for v1.** Duplicating the canvas editor (permanent edits deep-link
to `/workflows/{id}` in the web app); persistent on-page overlays; voice;
vision/OCR; browser automation (see Roadmap + automation-agent overlap note).

**Success criteria.** Run-from-panel round trip < 3 clicks; page capture never
reads form field values; zero background network activity when idle; a rate-limit
burst can never be produced by the extension (throttled sends, no auto-retry).

## 2. Architecture

```
┌────────────── Chrome ──────────────────────────────────────────┐
│  Side panel (React)      Options (React)      Content capture  │
│  workflows/runs/chat     sign-in, URLs        (injected on     │
│  overrides, palette      permissions          demand, exits)   │
│        │  chrome.storage (single source of truth)  │           │
│        └───────────── Service worker ──────────────┘           │
│              capture orchestration, context menus              │
└───────────────┬────────────────────────────────────────────────┘
                │ fetch (host_permissions ⇒ CORS-exempt), Bearer JWT
        Flask backend :5001 (fallback :10000)
        /auth/login /auth/me /workflows /workflows/:id/run(+param_overrides)
        /workflows/:id/runs /workflows/assistant
```

Principles: the MV3 worker is treated as **ephemeral** — no in-memory state
matters; `chrome.storage` is the source of truth and every page subscribes to
`storage.onChanged`. All fetches happen in extension contexts (worker/pages),
which host permissions exempt from CORS, so **zero backend CORS changes**.

## 3. UX flows

- **Launch**: toolbar click / Alt+X → side panel → Workflows tab → Run.
  Captured context (if any) is shown above the tabs and rides along.
- **Capture**: panel button / right-click menu / Alt+Shift+X → content script
  injected → context card fills in → cleared with one click.
- **Override**: expand a workflow → pick node → pick param (datalist from the
  saved graph) → value (JSON-parsed) → badge "overridden" appears → Run uses
  it → closes with the browser session.
- **Inspect**: any run finishing in the panel auto-jumps to Runs with that run
  expanded: per-node status, outputs, errors, token usage.
- **Assist**: Assistant tab, optional "include captured page" checkbox,
  3-second minimum send spacing.
- **Auth**: options page sign-in; 401 anywhere routes the user back there.

## 4. Wireframes

```
┌─────────────────────────────┐  ┌─────────────────────────────┐
│ ● Xoltra Companion  ⌘K  ⚙  │  │ ● Xoltra Companion  ⌘K  ⚙  │
│ ┃ Pricing – Acme    ✕      │  │ ┃ No page captured [Capture]│
│ ┃ 1,204 words · 37 links   │  ├─────────────────────────────┤
├─────────────────────────────┤  │ Workflows │ Runs │ Assistant│
│ Workflows │ Runs │ Assistant│  ├─────────────────────────────┤
├─────────────────────────────┤  │ ▼ success   Jul 20, 14:02   │
│ [search…]                   │  │   ● a1b2c3d4  success       │
│ ┌─────────────────────────┐ │  │   { "text": "…" }           │
│ │ Lead Qualifier  [pub]   │ │  │   ● e5f6a7b8  failed        │
│ │ 5 nodes   Edit  ▶ Run   │ │  │   ⚠ SERPAPI_API_KEY unset   │
│ │ ── session overrides ── │ │  │   tokens 1,204 · LLM 2      │
│ │ Web Search·num_results=3│ │  │ ▷ failed    Jul 19, 09:41   │
│ └─────────────────────────┘ │  └─────────────────────────────┘
└─────────────────────────────┘
```

## 5. Folder structure

```
browser-extension/
├── manifest.json          MV3 manifest (permissions-minimal)
├── build.mjs              esbuild pipeline → dist/ (Load unpacked)
├── package.json           react, react-dom; esbuild, typescript dev-only
├── tsconfig.json          strict, noUncheckedIndexedAccess
└── src/
    ├── shared/            types.ts · api.ts · storage.ts · messages.ts
    ├── background/        service-worker.ts
    ├── content/           capture.ts (on-demand, self-terminating)
    ├── sidepanel/         main.tsx · App.tsx · hooks.ts · sidepanel.{html,css}
    │   └── components/    WorkflowsView · RunsView · AssistantView · CommandPalette
    └── options/           main.tsx · options.html
```

## 6. API design

Consumed (all existing): `POST /api/auth/login`, `GET /api/auth/me`,
`GET /api/workflows`, `GET /api/workflows/:id`, `GET /api/workflows/:id/runs`,
`GET /api/workflows/:id/runs/:runId`, `POST /api/workflows/assistant`.

Extended (this project):

```
POST /api/workflows/:id/run
{ "trigger_data":    { "page_context": PageContext? , ... },
  "param_overrides": { "<node_id>": { "<param>": value } }?  }
```

`param_overrides` merges into a **run-local** copy of the graph inside
`workflow_engine.run_workflow()` (the store `json.loads`es the graph per call,
so nothing persists). Validated as an object in `workflow_routes.py`.

Error taxonomy handled by the client (`shared/api.ts`): 401 → re-login;
403 `TERMS_NOT_ACCEPTED` → directed to web app; 403 `timeout:true` →
suspended; 429 → **surfaced, never retried** (backend escalates repeat 429s
into account timeouts via `moderation.record_violation`).

## 7. State management

| State | Tier | Why |
|---|---|---|
| JWT (`xoltra_token`) | `storage.local` | survives restarts; same key name as web app |
| Settings (URLs) | `storage.local` | device-level config |
| Session overrides | `storage.session` | **session-only enforced by the storage tier**, not cleanup code |
| Captured page context | `storage.session` | transient by nature |
| UI state (tab, drafts) | React state | ephemeral |

Panel/options never share memory with the worker; they subscribe to
`chrome.storage.onChanged` + one `CONTEXT_UPDATED` broadcast. No state can
desync because nothing is cached outside storage.

## 8. Extension architecture (MV3 specifics)

- Worker is stateless and restart-safe; all listeners registered at top level.
- Content script injected **on demand only** (`activeTab` + `scripting`), an
  IIFE that extracts, messages back, and leaves nothing resident.
- `host_permissions` limited to the two localhost backends; anything else is
  an `optional_host_permissions` runtime grant from the options page.
- No remote code, no eval, no bundler dev-server (esbuild → flat `dist/`).

## 9. Session override model

`SessionOverrides = { workflowId: { nodeId: { paramKey: value } } }` in
`chrome.storage.session`. UI reads the saved graph for node/param
autocomplete; values JSON-parse with plain-string fallback. At run time the
map is sent as `param_overrides`; the backend merges into the run-local graph.
Guarantees: never persisted server-side, never survives the browser session,
visibly badged ("overridden") in the panel. Permanent editing is a deep link
to the real editor — one graph editor in the product, not two.

## 10. Security review

- **Least privilege**: no `<all_urls>`, no `tabs` read of every tab, no
  persistent content scripts. `activeTab` means page access only on explicit
  user gesture, only that tab.
- **Capture redaction**: `capture.ts` never reads inputs/textareas — form
  values (passwords, cards) structurally cannot enter a capture. Payload caps
  (4k excerpt / 2k selection) bound exfiltration surface and request size.
- **Token**: `storage.local`, not synced, never logged; sign-out wipes it.
  24h TTL server-side; 401 taxonomy forces clean re-login.
- **Rate-limit safety**: no automatic retry on any 4xx; assistant sends
  serialized + 3s spaced (backend suspends accounts on 429 bursts).
- **Origin trust**: custom backend URLs require an explicit per-origin
  permission grant; defaults are localhost only.
- Known residual risks: JWT in extension storage is readable by local
  processes with profile access (same as web localStorage today); backend dev
  JWT_SECRET default is a deployment concern outside this scope (flagged).

## 11. Performance review

- Idle cost ≈ 0: worker event-driven, dies after 30s; no polling loops.
- Bundles: sidepanel 210 KB, options 195 KB (React), worker 1.5 KB, capture
  script ~1 KB — all local, no network fonts/assets.
- Run inspection fetches details lazily per expanded run and memoizes.
- `/run` is synchronous server-side; the panel disables concurrent runs and
  shows progress instead of retrying (documented backend limitation).

## 12. Testing strategy

- `npm run typecheck` (strict TS) and `npm run build` gate every change — both green.
- Manual matrix (documented in README): sign-in/expiry/401 path, ToS-gate 403,
  capture on normal page / chrome:// (expected failure surfaced), run with and
  without overrides (verify via Runs tab node params), palette keyboard nav.
- Backend: `py_compile` green; override merge is pure-function-shaped —
  unit-testable as `run_workflow(param_overrides=...)` against a fixture graph.
- Future: Playwright + `chromium.launchPersistentContext` extension harness.

## 13. Browser compatibility

Chrome/Edge/Brave/Arc ≥ 120 (Side Panel API + `storage.session`;
`minimum_chrome_version` set). Firefox needs a sidebar-API port and MV3
event-page differences — out of scope v1, tracked in roadmap. Safari not
planned.

## 14. Roadmap

- **v0.1 (shipped)**: panel, capture, run + overrides, inspector, assistant,
  palette, options/auth.
- **v0.2**: run-again-with-overrides from a past run; per-site auto-capture
  opt-in; richer proposed-node → "create workflow" round trip; toolbar badge
  for failed runs.
- **v0.3**: workflow suggestions from page shape (rules first, LLM later);
  floating on-page quick launcher (opt-in per site); Firefox port.
- **v0.4**: observed-action → workflow generation (recorder), voice input,
  vision-model page understanding with OCR fallback — each behind its own
  permission prompt.

## 15. Risk analysis

| Risk | Severity | Mitigation |
|---|---|---|
| 429 → account suspension via moderation escalation | High | no auto-retry, throttled assistant, serialized runs |
| JWT 24h expiry, no refresh | Med | 401 taxonomy + one-click path to options sign-in |
| Synchronous `/run` timeouts on long workflows | Med | single-flight UI; backend async mode on roadmap |
| ToS version bump re-locks all API calls | Med | dedicated `terms` error state pointing to web app |
| automation-agent (:4000, unauthenticated, CORS *) overlap | Med | extension does NOT integrate with it; flagged for backend hardening |
| Backend URL misconfig (permission not granted) | Low | options page requests + verifies grants, explicit failure text |
| Chrome Side Panel API changes | Low | minimum version pinned; panel is plain HTML fallback-able |

---

## Innovation backlog (30+ candidates)

Grouped; ordered by value-to-effort within each group. Roadmap column keys to §14.

**Context & capture**
1. Selection-only capture mode (privacy floor) — v0.2
2. Auto-capture on navigation for allow-listed sites — v0.3
3. Table/list extraction into structured rows for loop nodes — v0.3
4. Screenshot region capture routed to a vision node — v0.4
5. PDF-in-tab text extraction — v0.3
6. Multi-tab capture (compare/merge two pages) — v0.4
7. Capture history (last N pages, session-scoped) — v0.2

**Running & inspecting**
8. Re-run with previous run's overrides — v0.2
9. Scheduled runs UI surfacing `trigger.schedule` cron — v0.2
10. Run diff: compare node outputs across two runs — v0.3
11. Toolbar badge + notification on failed runs — v0.2
12. Mid-run cancel (needs backend async mode first) — v0.4
13. Per-node re-run from the inspector — v0.4
14. Cost meter: token usage rollup per workflow per week — v0.3

**AI**
15. "Suggest a workflow for this page" (page shape → template match) — v0.3
16. Proposed-node → one-click create-workflow round trip — v0.2
17. Explain-this-run: assistant summarizes a failed run's cause — v0.3
18. Prompt-param preview: render Jinja templates against captured context before running — v0.3
19. Voice commands (Web Speech API, push-to-talk only) — v0.4
20. Observed-action recorder → draft workflow (n8n-killer feature; consent-heavy) — v0.4

**Workflow management**
21. Favorites/pinning + most-recently-run ordering — v0.2
22. Template gallery browse/instantiate from panel — v0.3
23. Quick-create: name + trigger picker without opening the editor — v0.3
24. Workflow health indicators (last-run status inline) — v0.2

**Platform & enterprise**
25. Org switcher once backend teams API lands in the panel — v0.3
26. Encrypted secrets vault handshake (never store raw secrets in overrides; reference `secure-api` KV instead — also gives the orphaned `backend/secure-api` service a purpose) — v0.4
27. Audit trail viewer (who ran what from which page) — v0.3
28. SSO/OAuth device-code sign-in replacing password entry — v0.3
29. Offline queue: capture + queue runs while backend unreachable — v0.4
30. Firefox port (sidebar API) — v0.3
31. Keyboard-only mode certification + screen-reader pass (WCAG) — v0.2
32. Session-override sharing: export overrides as a URL-safe blob a teammate can import — v0.4

**Challenged assumptions.** (a) The master prompt lists browser automation —
the audit found `automation-agent`'s Puppeteer connector already owns that
lane; duplicating it in-extension splits one capability across two engines,
so v1 deliberately defers and the right end-state is the extension acting as
the *executor* for that connector in real tabs. (b) "Floating AI assistant on
every page" conflicts with the permissions-minimal stance that enterprise
review demands; the side panel delivers the same capability with zero ambient
page presence, so the overlay ships later as opt-in per site rather than
default-on.
