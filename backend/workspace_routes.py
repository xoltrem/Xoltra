"""
workspace_routes.py — Xoltra Autonomous Workspace API.

Flask routes exposing the workspace engine. Register with
register_workspace_routes(app) in app.py — same pattern as
simulation_routes.py / workflow_routes.py.

Endpoints:
    GET  /api/workspace/tree                     — file tree
    GET  /api/workspace/file?path=               — read file
    POST /api/workspace/file                     — write file  {path, content}
    POST /api/workspace/mkdir                    — {path}
    POST /api/workspace/move                     — {path, to}
    POST /api/workspace/delete                   — {path}
    GET  /api/workspace/search?q=                — symbol/path/content search
    GET  /api/workspace/search/semantic?q=       — embedding search (lexical fallback)
    GET  /api/workspace/changes?since=N          — change feed for live UI updates
    GET  /api/workspace/tasks                    — background task list
    GET  /api/workspace/tasks/<id>               — task status/steps/result
    POST /api/workspace/agent/tasks              — submit background agent task
    GET  /api/workspace/graph                    — dependency graph JSON
    POST /api/workspace/index                    — rebuild index
    POST /api/workspace/agent/stream             — NL instruction, SSE progress
    GET  /api/workspace/patches                  — list patches
    GET  /api/workspace/patches/<id>             — patch detail (diffs)
    POST /api/workspace/patches/<id>/apply       — apply approved patch
    POST /api/workspace/patches/<id>/rollback    — undo applied patch
    GET  /api/workspace/checkpoints              — list checkpoints
    POST /api/workspace/checkpoints/<id>/rollback
    POST /api/workspace/terminal                 — {command} allowlisted exec
    GET  /api/workspace/git/status
    POST /api/workspace/git/commit               — {message, paths?}
    POST /api/workspace/git/push                 — {remote?, branch?}
    POST /api/workspace/git/pull

Workspace root defaults to the repo containing this backend; override
with WORKSPACE_ROOT env var.
"""

import json as _json
import logging
import os
import queue
import threading
import traceback
from pathlib import Path

from flask import request, jsonify, Response, stream_with_context

from auth import require_auth
from rate_limit import rate_limit_user

from workspace.security import WorkspaceSecurity, WorkspaceSecurityError
from workspace.fs_ops import FsOps
from workspace.indexer import RepoIndexer
from workspace.dep_graph import DependencyGraph
from workspace.checkpoints import CheckpointStore
from workspace.patcher import Patcher, PatchValidationError
from workspace.terminal import Terminal, TerminalError
from workspace.semantic import SemanticSearch
from workspace.tasks import TaskManager, ChangeFeed
from workspace.agent import WorkspaceAgent

logger = logging.getLogger(__name__)

_engine = {}


def _get_engine():
    """Lazy singleton — builds on first request so a bad WORKSPACE_ROOT
    fails the endpoint, not app boot."""
    if "agent" not in _engine:
        root = os.getenv("WORKSPACE_ROOT") or str(Path(__file__).resolve().parent.parent)
        sec = WorkspaceSecurity(root)
        fs = FsOps(sec)
        indexer = RepoIndexer(sec)
        deps = DependencyGraph(sec, indexer)
        cps = CheckpointStore(sec)
        feed = ChangeFeed()
        patcher = Patcher(sec, fs, cps, deps, change_feed=feed)
        _engine.update({
            "sec": sec, "fs": fs, "indexer": indexer, "deps": deps,
            "cps": cps, "patcher": patcher, "terminal": Terminal(sec),
            "semantic": SemanticSearch(sec, indexer),
            "tasks": TaskManager(), "feed": feed,
            "agent": WorkspaceAgent(sec, fs, indexer, deps, patcher),
        })
    return _engine


def _err(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


def _ok(data: dict):
    return jsonify({"success": True, **data})


def register_workspace_routes(app):

    # ── files ──────────────────────────────────────────────

    @app.route("/api/workspace/tree", methods=["GET"])
    @require_auth
    def ws_tree():
        try:
            return _ok({"tree": _get_engine()["fs"].tree()})
        except Exception as e:
            return _err(str(e), 500)

    @app.route("/api/workspace/file", methods=["GET"])
    @require_auth
    def ws_read_file():
        path = request.args.get("path", "")
        try:
            e = _get_engine()
            return _ok({"path": path, "content": e["fs"].read_file(path)})
        except FileNotFoundError:
            return _err(f"Not found: {path}", 404)
        except WorkspaceSecurityError as ex:
            return _err(str(ex), 403)

    @app.route("/api/workspace/file", methods=["POST"])
    @require_auth
    @rate_limit_user(30, 60, category="ai_flood")
    def ws_write_file():
        body = request.get_json(silent=True) or {}
        path, content = body.get("path", ""), body.get("content", "")
        if not path:
            return _err("path is required")
        try:
            e = _get_engine()
            patch = e["patcher"].propose(f"Edit {path}",
                                         [{"type": "write", "path": path, "content": content}],
                                         auto_update_imports=False)
            e["patcher"].apply(patch["id"])
            e["indexer"].invalidate(path)
            return _ok({"result": {"path": path}, "checkpoint_id": patch["checkpoint_id"]})
        except (WorkspaceSecurityError, PatchValidationError) as ex:
            return _err(str(ex), 403)

    @app.route("/api/workspace/mkdir", methods=["POST"])
    @require_auth
    def ws_mkdir():
        body = request.get_json(silent=True) or {}
        try:
            e = _get_engine()
            result = e["fs"].create_folder(body.get("path", ""))
            e["feed"].emit("mkdir", {"paths": [body.get("path", "")]})
            return _ok({"result": result})
        except WorkspaceSecurityError as ex:
            return _err(str(ex), 403)

    @app.route("/api/workspace/move", methods=["POST"])
    @require_auth
    @rate_limit_user(30, 60, category="ai_flood")
    def ws_move():
        body = request.get_json(silent=True) or {}
        src, dst = body.get("path", ""), body.get("to", "")
        if not src or not dst:
            return _err("path and to are required")
        try:
            e = _get_engine()
            e["indexer"].build(); e["deps"].build()
            patch = e["patcher"].propose(f"Move {src} -> {dst}",
                                         [{"type": "move", "path": src, "to": dst}])
            e["patcher"].apply(patch["id"])
            e["indexer"].build(); e["deps"].build()
            return _ok({"patch": _slim(patch)})
        except (WorkspaceSecurityError, PatchValidationError, FileNotFoundError, FileExistsError) as ex:
            return _err(str(ex), 400)

    @app.route("/api/workspace/delete", methods=["POST"])
    @require_auth
    @rate_limit_user(30, 60, category="ai_flood")
    def ws_delete():
        body = request.get_json(silent=True) or {}
        path = body.get("path", "")
        if not path:
            return _err("path is required")
        try:
            e = _get_engine()
            e["indexer"].build(); e["deps"].build()
            patch = e["patcher"].propose(f"Delete {path}", [{"type": "delete", "path": path}])
            e["patcher"].apply(patch["id"])
            e["indexer"].invalidate(path)
            return _ok({"patch": _slim(patch)})
        except (WorkspaceSecurityError, PatchValidationError, FileNotFoundError) as ex:
            return _err(str(ex), 400)

    # ── index / search / graph ─────────────────────────────

    @app.route("/api/workspace/index", methods=["POST"])
    @require_auth
    def ws_index():
        e = _get_engine()
        stats = e["indexer"].build(force=True)
        graph = e["deps"].build()
        return _ok({"index": stats, "graph": graph})

    @app.route("/api/workspace/search", methods=["GET"])
    @require_auth
    def ws_search():
        q = request.args.get("q", "").strip()
        if not q:
            return _err("q is required")
        e = _get_engine()
        if not e["indexer"].files:
            e["indexer"].build()
        return _ok({"results": e["indexer"].search(q)})

    @app.route("/api/workspace/search/semantic", methods=["GET"])
    @require_auth
    @rate_limit_user(30, 60, category="ai_flood")
    def ws_search_semantic():
        q = request.args.get("q", "").strip()
        if not q:
            return _err("q is required")
        return _ok(_get_engine()["semantic"].search(q))

    @app.route("/api/workspace/changes", methods=["GET"])
    @require_auth
    def ws_changes():
        try:
            since = int(request.args.get("since", 0))
        except ValueError:
            since = 0
        return _ok(_get_engine()["feed"].since(since))

    @app.route("/api/workspace/tasks", methods=["GET"])
    @require_auth
    def ws_tasks():
        return _ok({"tasks": _get_engine()["tasks"].list()})

    @app.route("/api/workspace/tasks/<task_id>", methods=["GET"])
    @require_auth
    def ws_task_detail(task_id):
        t = _get_engine()["tasks"].get(task_id)
        if not t:
            return _err("Task not found", 404)
        if t.get("result") and isinstance(t["result"], dict) and "patch" in t["result"]:
            t["result"] = {"plan": t["result"].get("plan"),
                           "patch": _slim(t["result"]["patch"])}
        return _ok({"task": t})

    @app.route("/api/workspace/agent/tasks", methods=["POST"])
    @require_auth
    @rate_limit_user(30, 60, category="ai_flood")
    def ws_agent_task():
        """Background alternative to /agent/stream: submit and poll
        /tasks/<id> — multiple instructions can run concurrently
        (planning/generation parallel; applies serialized by the
        mutation lock)."""
        body = request.get_json(silent=True) or {}
        instruction = (body.get("instruction") or "").strip()
        if not instruction:
            return _err("instruction is required")
        e = _get_engine()
        task_id = e["tasks"].submit(
            instruction[:80],
            lambda on_step: e["agent"].run(instruction, on_step=on_step,
                                           auto_apply=bool(body.get("auto_apply", False))),
        )
        return _ok({"task_id": task_id})

    @app.route("/api/workspace/graph", methods=["GET"])
    @require_auth
    def ws_graph():
        e = _get_engine()
        if not e["deps"].imports:
            e["indexer"].build(); e["deps"].build()
        return _ok({"graph": e["deps"].graph_json()})

    # ── agent (SSE) ────────────────────────────────────────

    @app.route("/api/workspace/agent/stream", methods=["POST"])
    @require_auth
    @rate_limit_user(30, 60, category="ai_flood")
    def ws_agent_stream():
        body = request.get_json(silent=True) or {}
        instruction = (body.get("instruction") or "").strip()
        auto_apply = bool(body.get("auto_apply", False))
        if not instruction:
            return _err("instruction is required")

        e = _get_engine()

        def generate():
            step_queue: "queue.Queue" = queue.Queue()
            outcome = {}

            def on_step(name, data):
                step_queue.put(("step", {"step": name, **data}))

            def worker():
                try:
                    outcome["result"] = e["agent"].run(instruction, on_step=on_step,
                                                      auto_apply=auto_apply)
                except Exception as ex:
                    outcome["error"] = str(ex)
                    logger.error(f"[workspace agent] {ex}\n{traceback.format_exc()}")
                finally:
                    step_queue.put(("__done__", None))

            threading.Thread(target=worker, daemon=True).start()

            while True:
                event, payload = step_queue.get()
                if event == "__done__":
                    break
                yield f"event: {event}\ndata: {_json.dumps(payload)}\n\n"

            if "error" in outcome:
                yield f"event: error\ndata: {_json.dumps({'error': outcome['error']})}\n\n"
            else:
                r = outcome["result"]
                yield "event: done\ndata: " + _json.dumps({
                    "plan": r["plan"], "patch": _slim(r["patch"]),
                }) + "\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── patches ────────────────────────────────────────────

    @app.route("/api/workspace/patches", methods=["GET"])
    @require_auth
    def ws_patches():
        e = _get_engine()
        return _ok({"patches": [_slim(p, diffs=False)
                                for p in sorted(e["patcher"].patches.values(),
                                                key=lambda p: -p["created"])]})

    @app.route("/api/workspace/patches/<patch_id>", methods=["GET"])
    @require_auth
    def ws_patch_detail(patch_id):
        p = _get_engine()["patcher"].patches.get(patch_id)
        if not p:
            return _err("Patch not found", 404)
        return _ok({"patch": _slim(p)})

    @app.route("/api/workspace/patches/<patch_id>/apply", methods=["POST"])
    @require_auth
    @rate_limit_user(30, 60, category="ai_flood")
    def ws_patch_apply(patch_id):
        e = _get_engine()
        try:
            patch = e["patcher"].apply(patch_id)
            e["indexer"].build(); e["deps"].build()
            return _ok({"patch": _slim(patch)})
        except KeyError as ex:
            return _err(str(ex), 404)
        except PatchValidationError as ex:
            return _err(str(ex), 409)

    @app.route("/api/workspace/patches/<patch_id>/rollback", methods=["POST"])
    @require_auth
    def ws_patch_rollback(patch_id):
        e = _get_engine()
        try:
            result = e["patcher"].rollback(patch_id)
            e["indexer"].build(); e["deps"].build()
            return _ok({"result": result})
        except KeyError as ex:
            return _err(str(ex), 404)

    # ── checkpoints ────────────────────────────────────────

    @app.route("/api/workspace/checkpoints", methods=["GET"])
    @require_auth
    def ws_checkpoints():
        return _ok({"checkpoints": _get_engine()["cps"].list()})

    @app.route("/api/workspace/checkpoints/<cp_id>/rollback", methods=["POST"])
    @require_auth
    def ws_checkpoint_rollback(cp_id):
        try:
            return _ok({"result": _get_engine()["cps"].rollback(cp_id)})
        except KeyError as ex:
            return _err(str(ex), 404)

    # ── terminal / git ─────────────────────────────────────

    @app.route("/api/workspace/terminal", methods=["POST"])
    @require_auth
    @rate_limit_user(30, 60, category="ai_flood")
    def ws_terminal():
        body = request.get_json(silent=True) or {}
        command = (body.get("command") or "").strip()
        if not command:
            return _err("command is required")
        try:
            e = _get_engine()
            result = e["terminal"].run(command)
            e["feed"].emit("terminal", {"command": command, "exit_code": result["exit_code"]})
            return _ok({"result": result})
        except TerminalError as ex:
            return _err(str(ex), 403)

    @app.route("/api/workspace/git/status", methods=["GET"])
    @require_auth
    def ws_git_status():
        try:
            return _ok({"result": _get_engine()["terminal"].git_status()})
        except TerminalError as ex:
            return _err(str(ex), 500)

    @app.route("/api/workspace/git/commit", methods=["POST"])
    @require_auth
    @rate_limit_user(30, 60, category="ai_flood")
    def ws_git_commit():
        body = request.get_json(silent=True) or {}
        message = (body.get("message") or "").strip()
        if not message:
            return _err("message is required")
        try:
            return _ok({"result": _get_engine()["terminal"].git_commit(
                message, paths=body.get("paths"))})
        except (TerminalError, WorkspaceSecurityError) as ex:
            return _err(str(ex), 400)

    @app.route("/api/workspace/git/push", methods=["POST"])
    @require_auth
    @rate_limit_user(30, 60, category="ai_flood")
    def ws_git_push():
        body = request.get_json(silent=True) or {}
        try:
            return _ok({"result": _get_engine()["terminal"].git_push(
                body.get("remote", "origin"), body.get("branch"))})
        except TerminalError as ex:
            return _err(str(ex), 400)

    @app.route("/api/workspace/git/pull", methods=["POST"])
    @require_auth
    def ws_git_pull():
        try:
            return _ok({"result": _get_engine()["terminal"].git_pull()})
        except TerminalError as ex:
            return _err(str(ex), 400)

    logger.info("Workspace routes registered")


def _slim(patch: dict, diffs: bool = True) -> dict:
    """Patch without file contents (operations carry full new content —
    too big for list endpoints; the diff is what the UI shows)."""
    out = {k: patch[k] for k in ("id", "title", "created", "status", "checkpoint_id")}
    out["operation_count"] = len(patch["operations"])
    out["operations"] = [{k: v for k, v in op.items() if k != "content"}
                         for op in patch["operations"]]
    if diffs:
        out["diffs"] = patch["diffs"]
    return out
