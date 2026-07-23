# Autonomous Workspace Manipulation

Xoltra's built-in workspace engine: natural-language repository edits with
diffs, approval, and rollback — plus a full explorer/editor UI at `/workspace`.

## Architecture

```
frontend /workspace page
  FileTree · EditorPane · AgentPanel · DiffViewer
  stores/workspace.ts (zustand) · lib/workspaceApi.ts (REST + SSE)
        │
backend workspace_routes.py  (register_workspace_routes(app) in app.py)
        │
backend/workspace/
  security.py     path sandbox — every fs touch resolves through it
  fs_ops.py       create/read/write/move/delete files & folders
  indexer.py      repo scan, symbols (Python ast / TS regex), search
  dep_graph.py    import graph, blast-radius, auto import rewrite on move
  semantic.py     embedding search (Cohere, cached by mtime, lexical fallback)
  checkpoints.py  snapshot journal (.xoltra_checkpoints/), rollback
  patcher.py      diff generation, syntax validation, atomic apply
                  (serialized by the global mutation lock)
  terminal.py     allowlisted commands + git status/commit/push/pull
  tasks.py        TaskManager (bounded worker pool, poll-able status),
                  ChangeFeed (revision counter for live UI updates),
                  MUTATION_LOCK (serializes all writes)
  agent.py        NL instruction -> plan (call_architect) -> code
                  (call_coding) -> validated patch, streamed via SSE
```

## Concurrency

- Agent tasks can run in parallel via POST `/api/workspace/agent/tasks`
  (plan + generate concurrently, bounded pool of 3).
- Every apply/rollback holds `MUTATION_LOCK` — two tasks never write at
  the same time; the repo can't end up interleaved.

## Live updates

- Every mutation bumps the `ChangeFeed` revision.
- The frontend polls GET `/api/workspace/changes?since=N` every 4s while
  `/workspace` is open and refreshes the tree/patches/open (non-dirty)
  files only when the revision moved. Poll-based so it works on
  serverless where websockets don't.

## Safety model

- Every mutation goes through `Patcher`: snapshot first, validate all
  syntax (Python `ast`, JSON, TS brace balance), then apply; any failure
  mid-apply auto-rolls back the checkpoint.
- Deleting a file that other files import is rejected with the dependent list.
- Moving/renaming rewrites relative and `@/` imports in all dependents
  inside the same patch.
- The agent never applies its own patch — the user approves the diff in
  the UI (`auto_apply` exists for trusted automation).
- Terminal: allowlisted executables only, `shell=False`, cwd pinned to the
  workspace root, output capped.
- Sandbox: no path escapes, `.git` internals and `.env*` files write-protected.

## Deployment

- `WORKSPACE_ROOT` env var sets the managed repo (defaults to the repo
  containing the backend).
- No new Python dependencies — stdlib only.
- Serverless note: on read-only filesystems checkpoints degrade to
  in-memory (survive the request, not the instance); git history is the
  durable rollback layer there. Terminal/git need a host with a real fs
  and git binary — those routes return clean errors otherwise.

## API

See the docstring in `backend/workspace_routes.py` for the full endpoint list.
