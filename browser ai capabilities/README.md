# Xoltra — Permissioned Web & App Integration Agent

Long-running agent that connects to Gmail, Word, browser, Codex IDE, and Antigravity IDE with explicit user consent. Saves KB-sized checkpoints and resumes instantly after any disconnect.

## Structure

```
xoltra/
├── index.js                  ← Main entry + REST API (:4000)
├── package.json
├── core/
│   └── agent_core.js         ← Long-running agent engine
├── connectors/
│   └── index.js              ← Gmail · Word · Browser · Codex · Antigravity · Workflow
├── state/
│   └── persistence.js        ← Compressed checkpoint storage (.xoltra/)
├── roles/
│   └── role_manager.js       ← .role file watcher (live reload)
├── workflow/
│   └── builder.js            ← Multi-step workflow templates
└── dashboard/
    ├── App.jsx               ← React dashboard UI
    ├── index.html
    ├── vite.config.js
    └── package.json
```

## Quick Start

### Backend (Agent)
```bash
npm install
npm start
# Agent API → http://localhost:4000
```

### Dashboard (UI)
```bash
cd dashboard
npm install
npm run dev
# UI → http://localhost:5173
```

## REST API

| Method | Path | Description |
|--------|------|-------------|
| GET | /status | Full agent status |
| POST | /agent/start | Start agent |
| POST | /agent/pause | Pause + save state |
| POST | /agent/resume | Resume from checkpoint |
| POST | /agent/stop | Stop agent |
| POST | /tasks | Add task `{ title, connector, instructions }` |
| DELETE | /tasks/:id | Cancel task |
| POST | /permissions/grant | Grant connector access `{ connectorId }` |
| POST | /permissions/revoke | Revoke connector access `{ connectorId }` |
| GET | /workflows | List workflow templates |
| POST | /workflows/:id/run | Run a workflow |
| GET | /roles | List loaded role files |
| GET | /connectors | List connector info |

## Connectors

| ID | Service | Notes |
|----|---------|-------|
| `gmail` | Gmail | Requires Google OAuth2 credentials |
| `word` | Microsoft Word | Requires Microsoft Graph token |
| `browser` | Web Browser | Uses Puppeteer (headless Chrome) |
| `codex` | Codex IDE | HTTP to Codex agent at `localhost:3001` |
| `antigravity` | Antigravity IDE | HTTP to AG agent at `localhost:3002` |
| `workflow` | Workflow Builder | Self-contained, always active via role file |

## Role Files

Drop any `.role` file into `.xoltra/roles/` — changes are applied instantly without restart.

`workflow_builder.role` is seeded automatically on first run and enables the Workflow Builder connector.

### Role file format (JSON):
```json
{
  "active": true,
  "description": "My custom role",
  "permissions": ["read_email", "send_email"],
  "connectors": ["gmail"],
  "capabilities": ["*"]
}
```

## Persistence & Resume

State is saved to `.xoltra/` as a gzip-compressed JSON file (hard cap: 512 KB).
Per-task checkpoints are saved to `.xoltra/checkpoints/<taskId>.ckpt`.

On SIGINT/SIGTERM the agent pauses (not stops), preserving all in-flight task state.
On next `agent.start()` every paused task resumes from its exact checkpoint step.

## Credentials

Set via environment variables or pass directly to `connector.connect(creds)`:

```bash
# Gmail
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REDIRECT_URI=http://localhost:4000/oauth/gmail
GMAIL_REFRESH_TOKEN=...

# Microsoft Word
WORD_ACCESS_TOKEN=...

# Codex IDE
CODEX_API_URL=http://localhost:3001
CODEX_API_KEY=...

# Antigravity IDE
ANTIGRAVITY_API_URL=http://localhost:3002
ANTIGRAVITY_API_KEY=...
```
