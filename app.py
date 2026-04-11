"""
app.py — XoltaOS Flask API
Serves the React frontend on localhost:5001.
"""

import os
import json
import logging
import traceback

from flask import Flask, request, jsonify
from flask_cors import CORS

import knowledge_db as kdb
from pipeline import get_pipeline
from roles import get_all_roles, is_valid_role, get_role

# ═══════════════════════════════════════════════════
# APP SETUP
# ═══════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["http://localhost:3000", "http://localhost:5173"])

kdb.init_storage()
pipeline = get_pipeline()


# ═══════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════

def _err(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status

def _ok(data: dict):
    return jsonify({"success": True, **data})


# ═══════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════

@app.route("/api/health", methods=["GET"])
def health():
    try:
        stats = kdb.get_stats()
        return _ok({"status": "ok", "knowledge_stats": stats})
    except Exception as e:
        return _err(f"Health check failed: {e}", 500)


# ═══════════════════════════════════════════════════
# ROLES
# ═══════════════════════════════════════════════════

@app.route("/api/roles", methods=["GET"])
def list_roles():
    """Returns all available roles. Frontend uses this to populate the RoleSelector."""
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


# ═══════════════════════════════════════════════════
# GOAL PIPELINE
# ═══════════════════════════════════════════════════

@app.route("/api/clarify", methods=["POST"])
def clarify():
    """
    Step 1 of goal flow.
    Body: { "goal": "string", "role_id": "default" }
    """
    body    = request.get_json(silent=True) or {}
    goal    = (body.get("goal") or "").strip()
    role_id = body.get("role_id", "default")

    if not goal:
        return _err("goal is required")

    if not is_valid_role(role_id):
        role_id = "default"

    try:
        result = pipeline.get_clarifications(goal, role_id=role_id)
        return _ok({
            "mode":      result.get("mode", "default"),
            "questions": result.get("questions", [])
        })
    except Exception as e:
        logger.error(f"[/api/clarify] {e}\n{traceback.format_exc()}")
        return _err(f"Clarification failed: {e}", 500)


@app.route("/api/run", methods=["POST"])
def run_goal():
    """
    Step 2 of goal flow.
    Body: { "goal", "mode", "answers", "role_id" }
    """
    body    = request.get_json(silent=True) or {}
    goal    = (body.get("goal") or "").strip()
    mode    = body.get("mode", "default")
    answers = body.get("answers", {})
    role_id = body.get("role_id", "default")

    if not goal:
        return _err("goal is required")
    if mode not in ("default", "coach"):
        return _err("mode must be 'default' or 'coach'")
    if not is_valid_role(role_id):
        role_id = "default"

    try:
        result = pipeline.run(goal, mode=mode, answers=answers, role_id=role_id)
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


# ═══════════════════════════════════════════════════
# DOCUMENT PIPELINE
# ═══════════════════════════════════════════════════

@app.route("/api/run-document", methods=["POST"])
def run_document():
    """Body: { "text": "raw document text", "role_id": "default" }"""
    body    = request.get_json(silent=True) or {}
    text    = (body.get("text") or "").strip()
    role_id = body.get("role_id", "default")

    if not text:
        return _err("text is required")
    if not is_valid_role(role_id):
        role_id = "default"

    try:
        result = pipeline.run_from_document(text, role_id=role_id)
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
def upload_document():
    """Accepts a file upload (.txt, .md, .pdf) + optional role_id form field."""
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
                raw_text = "\n".join(
                    p.extract_text() for p in reader.pages if p.extract_text()
                )
            except ImportError:
                return _err("pypdf not installed — PDF support unavailable", 500)
        else:
            raw_text = file.read().decode("utf-8", errors="ignore")

        if not raw_text.strip():
            return _err("Could not extract text from file")

        result = pipeline.run_from_document(raw_text, role_id=role_id)
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


# ═══════════════════════════════════════════════════
# Q&A
# ═══════════════════════════════════════════════════

@app.route("/api/qa", methods=["POST"])
def qa():
    """Body: { "question": "string", "role_id": "default" }"""
    body     = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    role_id  = body.get("role_id", "default")

    if not question:
        return _err("question is required")
    if not is_valid_role(role_id):
        role_id = "default"

    try:
        result = pipeline.run_adaptive(question, role_id=role_id)
        return _ok({
            "output":  result.get("output", ""),
            "mode":    result.get("mode", "default"),
            "role_id": result.get("role_id", role_id),
        })
    except Exception as e:
        logger.error(f"[/api/qa] {e}\n{traceback.format_exc()}")
        return _err(f"Q&A failed: {e}", 500)


# ═══════════════════════════════════════════════════
# KNOWLEDGE / STATS
# ═══════════════════════════════════════════════════

@app.route("/api/stats", methods=["GET"])
def stats():
    try:
        return _ok({"stats": kdb.get_stats()})
    except Exception as e:
        return _err(f"Stats failed: {e}", 500)


@app.route("/api/knowledge/nodes", methods=["GET"])
def get_nodes():
    node_type = request.args.get("type", "goal")
    try:
        nodes = kdb.get_nodes_by_type(node_type)
        return _ok({"nodes": nodes, "count": len(nodes)})
    except Exception as e:
        return _err(f"Failed to fetch nodes: {e}", 500)


@app.route("/api/knowledge/nodes/<node_id>", methods=["GET"])
def get_node(node_id: str):
    try:
        node = kdb.get_node(node_id)
        if not node:
            return _err("Node not found", 404)
        return _ok({"node": node})
    except Exception as e:
        return _err(f"Failed to fetch node: {e}", 500)


# ═══════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"[XoltaOS] Starting on port {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
