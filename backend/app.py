"""
app.py — XoltaOS Flask API
Serves the frontend on localhost:5001.

Bugs fixed:
- register_simulation_routes(app) was called with no import → NameError on boot
- subscription_manager (tiers/usage) was never registered or initialized
- workflow_routes (workflow CRUD + run engine) was never registered
- personalization (xoltra-ai backend) added and registered
"""

import os
import logging
import traceback
import threading
import queue
import json as _json

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

import knowledge_db as kdb
import xoltra_knowledge_engine as xke
from pipeline import get_pipeline
from roles import get_all_roles, is_valid_role, get_role

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
_cors_origins = os.getenv("FRONTEND_URLS", "http://localhost:3000,http://localhost:5173").split(",")
CORS(app, origins=[o.strip() for o in _cors_origins if o.strip()])

kdb.init_storage()

import unity_bridge
from simulation_routes import register_simulation_routes
from workflow_routes import register_workflow_routes
from auth import auth_bp, init_auth_tables, require_auth, get_current_user_id
from rate_limit import rate_limit_user
from subscription_manager import subscription_bp, init_subs_tables
from personalization import personalization_bp, init_personalization_tables

from workflow_assistant import handle_assistant_message
import workflow_import
from digest import register_digest_routes

app.register_blueprint(auth_bp)
app.register_blueprint(subscription_bp)
app.register_blueprint(personalization_bp)

init_auth_tables()
init_subs_tables()
init_personalization_tables()

register_simulation_routes(app)
register_workflow_routes(app)
unity_bridge.start_bridge()

from backup_service import start_backup_scheduler
start_backup_scheduler()

from admin_routes import register_admin_routes
register_admin_routes(app)

from templates import register_template_routes
register_template_routes(app)

from referrals import register_referral_routes
register_referral_routes(app)

from teams import register_team_routes
register_team_routes(app)

from onedrive_routes import register_onedrive_routes
register_onedrive_routes(app)

register_digest_routes(app)

pipeline = get_pipeline()


def _err(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status

def _ok(data: dict):
    return jsonify({"success": True, **data})


@app.route("/api/health", methods=["GET"])
@require_auth
def health():
    user_id = get_current_user_id()
    try:
        stats = kdb.get_stats(user_id)
        return _ok({"status": "ok", "knowledge_stats": stats})
    except Exception as e:
        return _err(f"Health check failed: {e}", 500)


@app.route("/api/roles", methods=["GET"])
def list_roles():
    return _ok({"roles": get_all_roles()})


@app.route("/api/roles/<role_id>", methods=["GET"])
def get_role_detail(role_id: str):
    if not is_valid_role(role_id):
        return _err(f"Unknown role: {role_id}", 404)
    role = get_role(role_id)
    return _ok({
        "role": {
            "id":              role["id"],
            "name":            role["name"],
            "description":     role["description"],
            "icon":            role["icon"],
            "tone":            role["tone"],
            "expertise_areas": role["expertise_areas"],
        }
    })


@app.route("/api/clarify", methods=["POST"])
@require_auth
def clarify():
    user_id = get_current_user_id()
    body    = request.get_json(silent=True) or {}
    goal    = (body.get("goal") or "").strip()
    role_id = body.get("role_id", "default")

    if not goal:
        return _err("goal is required")
    if not is_valid_role(role_id):
        role_id = "default"

    try:
        result = pipeline.get_clarifications(user_id, goal, role_id=role_id)
        return _ok({"mode": result.get("mode", "default"), "questions": result.get("questions", [])})
    except Exception as e:
        logger.error(f"[/api/clarify] {e}\n{traceback.format_exc()}")
        return _err(f"Clarification failed: {e}", 500)


@app.route("/api/run", methods=["POST"])
@require_auth
@rate_limit_user(20, 60, category="ai_flood")
def run_goal():
    user_id    = get_current_user_id()
    body       = request.get_json(silent=True) or {}
    goal       = (body.get("goal") or "").strip()
    mode       = body.get("mode", "default")
    answers    = body.get("answers", {})
    role_id    = body.get("role_id", "default")
    thread_id  = body.get("conversation_id") or body.get("thread_id")

    if not goal:
        return _err("goal is required")
    if mode not in ("default", "coach"):
        return _err("mode must be 'default' or 'coach'")
    if not is_valid_role(role_id):
        role_id = "default"

    try:
        result = pipeline.run(user_id, goal, mode=mode, answers=answers, role_id=role_id, thread_id=thread_id)
        return _ok({
            "output":        result.get("output", ""),
            "output_parsed": result.get("output_parsed"),
            "mode":          result.get("mode", mode),
            "role_id":       result.get("role_id", role_id),
            "critic_status": result.get("critic_status"),
            "operator_used": result.get("operator_used", False),
            "critic_issues": result.get("critic_issues", []),
            "error":         result.get("error"),
        })
    except Exception as e:
        logger.error(f"[/api/run] {e}\n{traceback.format_exc()}")
        return _err(f"Pipeline failed: {e}", 500)


@app.route("/api/run/stream", methods=["POST"])
@require_auth
@rate_limit_user(20, 60, category="ai_flood")
def run_goal_stream():
    """
    Same as /api/run, but streams each pipeline stage (Router, Clarifier,
    Architect...) as it happens via Server-Sent Events, so a long run feels
    responsive instead of one long spinner. EventSource can't send a POST
    body or an Authorization header, so the client reads this with fetch()
    + a stream reader instead of `new EventSource(...)`.

    Event stream shape:
      event: step   data: {"step": "Architect"}         (zero or more)
      event: done   data: {...same shape as /api/run}    (exactly one, on success)
      event: error  data: {"error": "..."}                (exactly one, on failure)
    """
    user_id   = get_current_user_id()
    body      = request.get_json(silent=True) or {}
    goal      = (body.get("goal") or "").strip()
    mode      = body.get("mode", "default")
    answers   = body.get("answers", {})
    role_id   = body.get("role_id", "default")
    thread_id = body.get("conversation_id") or body.get("thread_id")

    if not goal:
        return _err("goal is required")
    if mode not in ("default", "coach"):
        return _err("mode must be 'default' or 'coach'")
    if not is_valid_role(role_id):
        role_id = "default"

    def generate():
        step_queue: "queue.Queue" = queue.Queue()
        outcome = {}

        def on_step(name):
            step_queue.put(("step", {"step": name}))

        def worker():
            try:
                result = pipeline.run(
                    user_id, goal, mode=mode, answers=answers,
                    role_id=role_id, thread_id=thread_id, on_step=on_step,
                )
                outcome["result"] = result
            except Exception as e:
                outcome["error"] = str(e)
                logger.error(f"[/api/run/stream] {e}\n{traceback.format_exc()}")
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
            result = outcome.get("result", {})
            yield "event: done\ndata: " + _json.dumps({
                "output":        result.get("output", ""),
                "output_parsed": result.get("output_parsed"),
                "mode":          result.get("mode", mode),
                "role_id":       result.get("role_id", role_id),
                "critic_status": result.get("critic_status"),
                "operator_used": result.get("operator_used", False),
                "critic_issues": result.get("critic_issues", []),
                "error":         result.get("error"),
            }) + "\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/run-document", methods=["POST"])
@require_auth
def run_document():
    user_id = get_current_user_id()
    body    = request.get_json(silent=True) or {}
    text    = (body.get("text") or "").strip()
    role_id = body.get("role_id", "default")

    if not text:
        return _err("text is required")
    if not is_valid_role(role_id):
        role_id = "default"

    try:
        result = pipeline.run_from_document(user_id, text, role_id=role_id)
        return _ok({
            "extracted_goal": result.get("extracted_goal", ""),
            "output":         result.get("output", ""),
            "output_parsed":  result.get("output_parsed"),
            "mode":           result.get("mode", "default"),
            "role_id":        result.get("role_id", role_id),
            "critic_status":  result.get("critic_status"),
            "operator_used":  result.get("operator_used", False),
            "error":          result.get("error"),
        })
    except Exception as e:
        logger.error(f"[/api/run-document] {e}\n{traceback.format_exc()}")
        return _err(f"Document pipeline failed: {e}", 500)


@app.route("/api/upload-document", methods=["POST"])
@require_auth
def upload_document():
    user_id = get_current_user_id()
    if "file" not in request.files:
        return _err("No file provided")

    file     = request.files["file"]
    role_id  = request.form.get("role_id", "default")
    filename = file.filename or ""
    ext      = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ("txt", "md", "pdf"):
        return _err("Only .txt, .md, and .pdf files are supported")
    if not is_valid_role(role_id):
        role_id = "default"

    try:
        if ext == "pdf":
            try:
                import pypdf, io
                reader   = pypdf.PdfReader(io.BytesIO(file.read()))
                raw_text = "\n".join(p.extract_text() for p in reader.pages if p.extract_text())
            except ImportError:
                return _err("pypdf not installed — PDF support unavailable", 500)
        else:
            raw_text = file.read().decode("utf-8", errors="ignore")

        if not raw_text.strip():
            return _err("Could not extract text from file")

        result = pipeline.run_from_document(user_id, raw_text, role_id=role_id)
        return _ok({
            "extracted_goal": result.get("extracted_goal", ""),
            "output":         result.get("output", ""),
            "output_parsed":  result.get("output_parsed"),
            "mode":           result.get("mode", "default"),
            "role_id":        result.get("role_id", role_id),
            "critic_status":  result.get("critic_status"),
            "operator_used":  result.get("operator_used", False),
            "error":          result.get("error"),
        })
    except Exception as e:
        logger.error(f"[/api/upload-document] {e}\n{traceback.format_exc()}")
        return _err(f"Upload failed: {e}", 500)


@app.route("/api/qa", methods=["POST"])
@require_auth
@rate_limit_user(30, 60, category="ai_flood")
def qa():
    user_id  = get_current_user_id()
    body     = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    role_id  = body.get("role_id", "default")

    if not question:
        return _err("question is required")
    if not is_valid_role(role_id):
        role_id = "default"

    try:
        result = pipeline.run_adaptive(user_id, question, role_id=role_id)
        return _ok({"output": result.get("output", ""), "mode": result.get("mode", "default"), "role_id": result.get("role_id", role_id)})
    except Exception as e:
        logger.error(f"[/api/qa] {e}\n{traceback.format_exc()}")
        return _err(f"Q&A failed: {e}", 500)


@app.route("/api/workflows/assistant", methods=["POST"])
@require_auth
@rate_limit_user(30, 60, category="ai_flood")
def workflow_assistant_route():
    """Powers the 'Create Workflow' chat panel — proposes one node per turn for review."""
    user_id         = get_current_user_id()
    body            = request.get_json(silent=True) or {}
    message         = (body.get("message") or "").strip()
    role_id         = body.get("role_id", "default")
    conversation_id = body.get("conversation_id")

    if not message:
        return _err("message is required")
    if not is_valid_role(role_id):
        role_id = "default"

    try:
        result = handle_assistant_message(user_id, message, role_id=role_id, conversation_id=conversation_id)
        return _ok({"reply": result["reply"], "proposed_node": result["proposed_node"]})
    except Exception as e:
        logger.error(f"[/api/workflows/assistant] {e}\n{traceback.format_exc()}")
        return _err(f"Assistant failed: {e}", 500)


@app.route("/api/workflows/import/parse", methods=["POST"])
@require_auth
@rate_limit_user(10, 60, category="ai_flood")
def workflow_import_parse_route():
    """
    Powers the 'Rebuild your existing automation' onboarding flow. Takes a
    pasted n8n/Make export or a plain description and proposes an ordered
    set of Xoltra nodes — review-only, nothing is saved here.
    """
    user_id         = get_current_user_id()
    body            = request.get_json(silent=True) or {}
    source_text     = body.get("source_text") or ""
    conversation_id = body.get("conversation_id")

    if not source_text.strip():
        return _err("source_text is required")

    try:
        result = workflow_import.parse_import(user_id, source_text, conversation_id=conversation_id)
        return _ok(result)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error(f"[/api/workflows/import/parse] {e}\n{traceback.format_exc()}")
        return _err(f"Import failed: {e}", 500)


@app.route("/api/workflows/import/compile", methods=["POST"])
@require_auth
def workflow_import_compile_route():
    """
    Turns the steps the user actually accepted (after reviewing
    /import/parse's output) into a runnable {nodes, edges} graph. Kept
    deterministic and server-side rather than duplicated in the frontend —
    see workflow_import.py's module docstring for why.
    """
    body = request.get_json(silent=True) or {}
    accepted_steps = body.get("accepted_steps")

    if not isinstance(accepted_steps, list) or not accepted_steps:
        return _err("accepted_steps must be a non-empty list")

    try:
        graph = workflow_import.compile_steps_to_graph(accepted_steps)
        return _ok({"graph": graph})
    except Exception as e:
        logger.error(f"[/api/workflows/import/compile] {e}\n{traceback.format_exc()}")
        return _err(f"Compile failed: {e}", 500)


@app.route("/api/stats", methods=["GET"])
@require_auth
def stats():
    user_id = get_current_user_id()
    try:
        return _ok({"stats": kdb.get_stats(user_id)})
    except Exception as e:
        return _err(f"Stats failed: {e}", 500)


@app.route("/api/knowledge/nodes", methods=["GET"])
@require_auth
def get_nodes():
    user_id   = get_current_user_id()
    node_type = request.args.get("type", "goal")
    try:
        nodes = kdb.get_nodes_by_type(user_id, node_type)
        return _ok({"nodes": nodes, "count": len(nodes)})
    except Exception as e:
        return _err(f"Failed to fetch nodes: {e}", 500)


@app.route("/api/knowledge/nodes/<node_id>", methods=["GET"])
@require_auth
def get_node(node_id: str):
    user_id = get_current_user_id()
    try:
        node = kdb.get_node(user_id, node_id)
        if not node:
            return _err("Node not found", 404)
        return _ok({"node": node})
    except Exception as e:
        return _err(f"Failed to fetch node: {e}", 500)


@app.route("/api/knowledge/nodes/<node_id>/versions", methods=["GET"])
@require_auth
def get_node_versions_route(node_id: str):
    """History for the node inspector's version panel — current + archived, newest first."""
    user_id = get_current_user_id()
    try:
        versions = kdb.get_node_versions(user_id, node_id)
        if not versions:
            return _err("Node not found", 404)
        return _ok({"versions": versions})
    except Exception as e:
        return _err(f"Failed to fetch version history: {e}", 500)


@app.route("/api/knowledge/nodes/<node_id>/rollback", methods=["POST"])
@require_auth
def rollback_node_route(node_id: str):
    """Restores a node to a prior version. Body: { "version": <int> }"""
    user_id = get_current_user_id()
    body    = request.get_json(silent=True) or {}
    version = body.get("version")

    if not isinstance(version, int):
        return _err("version (integer) is required")

    try:
        ok = kdb.rollback_node_version(user_id, node_id, version)
        if not ok:
            return _err("Version not found for this node", 404)
        return _ok({"node_id": node_id, "rolled_back_to": version})
    except Exception as e:
        return _err(f"Rollback failed: {e}", 500)


@app.route("/api/knowledge/compact", methods=["POST"])
@require_auth
def compact_session():
    user_id       = get_current_user_id()
    body          = request.get_json(silent=True) or {}
    messages      = body.get("messages", [])
    session_topic = (body.get("session_topic") or "").strip() or None

    if not isinstance(messages, list) or len(messages) == 0:
        return _err("messages must be a non-empty array")

    valid_roles = {"user", "assistant", "system"}
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            return _err(f"messages[{i}] must be an object")
        if msg.get("role") not in valid_roles:
            return _err(f"messages[{i}].role must be 'user', 'assistant', or 'system'")
        if not isinstance(msg.get("content"), str):
            return _err(f"messages[{i}].content must be a string")

    try:
        result = xke.compact_session(user_id, messages, session_topic=session_topic)
        if result is None:
            return _ok({"saved": False, "reason": "Session too short — need at least 2 user messages"})
        return _ok({
            "saved":     True,
            "node_id":   result["node_id"],
            "node_type": result["node_type"],
            "title":     result["title"],
            "summary":   result["summary"],
            "linked":    result["linked"],
        })
    except Exception as e:
        logger.error(f"[/api/knowledge/compact] {e}\n{traceback.format_exc()}")
        return _err(f"Session compaction failed: {e}", 500)


@app.route("/api/knowledge/context", methods=["POST"])
@require_auth
def get_knowledge_context():
    user_id = get_current_user_id()
    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    mode    = body.get("mode", "fast")

    if not message:
        return _err("message is required")
    if mode not in ("fast", "thinking"):
        return _err("mode must be 'fast' or 'thinking'")

    try:
        raw_nodes = xke.get_context_by_mode(user_id, message, mode=mode)
        shaped = [{
            "type":          n.get("type", "unknown"),
            "summary":       _shape_node_summary(n),
            "relevance":     round(n.get("relevance", 0), 3),
            "context_layer": n.get("context_layer", "primary"),
            "created_at":    n.get("created_at", ""),
        } for n in raw_nodes]
        return _ok({"mode": mode, "nodes": shaped, "count": len(shaped)})
    except Exception as e:
        logger.error(f"[/api/knowledge/context] {e}\n{traceback.format_exc()}")
        return _err(f"Context retrieval failed: {e}", 500)


def _shape_node_summary(node: dict) -> str:
    content   = node.get("content", {})
    node_type = node.get("type", "")
    if node_type == "goal":
        return (content.get("clarified_goal") or content.get("title", ""))[:200]
    elif node_type == "workflow":
        phases = content.get("phases", [])
        names  = ", ".join(p.get("phase_name", "") for p in phases[:3])
        return f"{len(phases)}-phase plan: {names}"[:200]
    elif node_type == "document":
        return content.get("extracted_goal", "")[:200]
    elif node_type == "insight":
        return content.get("pattern", content.get("title", ""))[:200]
    else:
        return str(content)[:200]


if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"[XoltaOS] Starting on port {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
