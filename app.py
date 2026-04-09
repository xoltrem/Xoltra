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

# ═══════════════════════════════════════════════════
# APP SETUP
# ═══════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["http://localhost:3000", "http://localhost:5173"])  # React dev servers

# Initialize knowledge storage once at startup
kdb.init_storage()

# Single pipeline instance (thread-safe reads)
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
    """Quick liveness check — frontend polls this on load."""
    try:
        stats = kdb.get_stats()
        return _ok({
            "status": "ok",
            "knowledge_stats": stats
        })
    except Exception as e:
        return _err(f"Health check failed: {e}", 500)


# ═══════════════════════════════════════════════════
# GOAL PIPELINE
# ═══════════════════════════════════════════════════

@app.route("/api/clarify", methods=["POST"])
def clarify():
    """
    Step 1 of goal flow.
    Body: { "goal": "string" }
    Returns: { mode, questions[] }
    """
    body = request.get_json(silent=True) or {}
    goal = (body.get("goal") or "").strip()

    if not goal:
        return _err("goal is required")

    try:
        result = pipeline.get_clarifications(goal)
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
    Step 2 of goal flow — runs the full pipeline.
    Body: {
        "goal":    "string",
        "mode":    "default | coach",      (optional, default: "default")
        "answers": { "q1": "...", ... }    (optional)
    }
    Returns: full pipeline result
    """
    body    = request.get_json(silent=True) or {}
    goal    = (body.get("goal") or "").strip()
    mode    = body.get("mode", "default")
    answers = body.get("answers", {})

    if not goal:
        return _err("goal is required")

    if mode not in ("default", "coach"):
        return _err("mode must be 'default' or 'coach'")

    try:
        result = pipeline.run(goal, mode=mode, answers=answers)
        return _ok({
            "output":        result.get("output", ""),
            "output_parsed": result.get("output_parsed"),
            "mode":          result.get("mode", mode),
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
    """
    Accepts a plain-text document body and runs document pipeline.
    Body: { "text": "raw document text" }
    Returns: { extracted_goal, output, ... }
    """
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()

    if not text:
        return _err("text is required")

    try:
        result = pipeline.run_from_document(text)
        return _ok({
            "extracted_goal": result.get("extracted_goal", ""),
            "output":         result.get("output", ""),
            "output_parsed":  result.get("output_parsed"),
            "mode":           result.get("mode", "default"),
            "critic_status":  result.get("critic_status"),
            "operator_used":  result.get("operator_used", False),
            "error":          result.get("error"),
        })
    except Exception as e:
        logger.error(f"[/api/run-document] {e}\n{traceback.format_exc()}")
        return _err(f"Document pipeline failed: {e}", 500)


@app.route("/api/upload-document", methods=["POST"])
def upload_document():
    """
    Accepts a file upload (.txt, .md, .pdf).
    Extracts text and runs document pipeline.
    """
    if "file" not in request.files:
        return _err("No file provided")

    file = request.files["file"]
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ("txt", "md", "pdf"):
        return _err("Only .txt, .md, and .pdf files are supported")

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

        result = pipeline.run_from_document(raw_text)
        return _ok({
            "extracted_goal": result.get("extracted_goal", ""),
            "output":         result.get("output", ""),
            "output_parsed":  result.get("output_parsed"),
            "mode":           result.get("mode", "default"),
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
    """
    Q&A mode — single question, single answer.
    Body: { "question": "string" }
    Returns: { output, mode }
    """
    body     = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()

    if not question:
        return _err("question is required")

    try:
        result = pipeline.run_adaptive(question)
        return _ok({
            "output": result.get("output", ""),
            "mode":   result.get("mode", "default"),
        })
    except Exception as e:
        logger.error(f"[/api/qa] {e}\n{traceback.format_exc()}")
        return _err(f"Q&A failed: {e}", 500)


# ═══════════════════════════════════════════════════
# KNOWLEDGE / STATS
# ═══════════════════════════════════════════════════

@app.route("/api/stats", methods=["GET"])
def stats():
    """Returns knowledge graph stats."""
    try:
        return _ok({"stats": kdb.get_stats()})
    except Exception as e:
        return _err(f"Stats failed: {e}", 500)


@app.route("/api/knowledge/nodes", methods=["GET"])
def get_nodes():
    """
    Returns nodes by type.
    Query param: ?type=goal (default: goal)
    """
    node_type = request.args.get("type", "goal")
    try:
        nodes = kdb.get_nodes_by_type(node_type)
        return _ok({"nodes": nodes, "count": len(nodes)})
    except Exception as e:
        return _err(f"Failed to fetch nodes: {e}", 500)


@app.route("/api/knowledge/nodes/<node_id>", methods=["GET"])
def get_node(node_id: str):
    """Returns a single node by ID."""
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
    port = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"[XoltaOS] Starting on port {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
