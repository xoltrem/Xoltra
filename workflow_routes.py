"""
workflow_routes.py — Xoltra Workflow API Endpoints

Flask Blueprint exposing the workflow engine, store, and node library
to the frontend. Register with register_workflow_routes(app) in app.py —
same pattern as simulation_routes.py.

Endpoints:
    GET    /api/workflows              — list all workflows
    POST   /api/workflows              — create workflow
    GET    /api/workflows/<id>         — get workflow
    PUT    /api/workflows/<id>         — update workflow
    DELETE /api/workflows/<id>         — delete workflow
    POST   /api/workflows/<id>/run     — execute workflow
    GET    /api/workflows/<id>/runs    — list run history
    GET    /api/workflows/<id>/runs/<run_id>  — get single run result
    GET    /api/nodes                  — list all available node definitions

Add to app.py (after kdb.init_storage()):
    from workflow_routes import register_workflow_routes
    register_workflow_routes(app)
"""

import logging
import traceback
import threading

from flask import Blueprint, request, jsonify

import workflow_store
import workflow_engine
import node_library
import knowledge_db as kdb
from auth import require_auth, get_current_user_id

logger = logging.getLogger(__name__)

_wf_bp = Blueprint("workflows", __name__)


# ═══════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════

def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


def _ok(data: dict):
    return jsonify({"success": True, **data})


# ═══════════════════════════════════════════════════
# WORKFLOW CRUD
# ═══════════════════════════════════════════════════

@_wf_bp.route("/api/workflows", methods=["GET"])
@require_auth
def list_workflows():
    """
    List all workflows.
    Query param: ?status=draft|published (optional)
    """
    user_id = get_current_user_id()
    status_filter = request.args.get("status")
    try:
        workflows = workflow_store.list_workflows(user_id, status=status_filter)
        return _ok({"workflows": workflows, "count": len(workflows)})
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error(f"[/api/workflows GET] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


@_wf_bp.route("/api/workflows", methods=["POST"])
@require_auth
def create_workflow():
    """
    Create a new workflow.
    Body: { "name": str, "status": "draft"|"published", "graph": { "nodes": [], "edges": [] } }
    """
    user_id = get_current_user_id()
    body = request.get_json(silent=True) or {}

    name = (body.get("name") or "").strip()
    if not name:
        return _err("'name' is required")

    try:
        workflow_id = workflow_store.save_workflow(user_id, {
            "name":   name,
            "status": body.get("status", "draft"),
            "graph":  body.get("graph", {"nodes": [], "edges": []}),
        })
        workflow = workflow_store.get_workflow(user_id, workflow_id)
        return _ok({"workflow": workflow}), 201
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error(f"[/api/workflows POST] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


@_wf_bp.route("/api/workflows/<workflow_id>", methods=["GET"])
@require_auth
def get_workflow(workflow_id: str):
    """Get a single workflow by ID."""
    user_id = get_current_user_id()
    try:
        workflow = workflow_store.get_workflow(user_id, workflow_id)
        if not workflow:
            return _err("Workflow not found", 404)
        return _ok({"workflow": workflow})
    except Exception as e:
        logger.error(f"[/api/workflows/{workflow_id} GET] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


@_wf_bp.route("/api/workflows/<workflow_id>", methods=["PUT"])
@require_auth
def update_workflow(workflow_id: str):
    """
    Update an existing workflow.
    Body: { "name": str, "status": str, "graph": {} }
    All fields are optional — only provided fields are updated.
    """
    user_id = get_current_user_id()
    body = request.get_json(silent=True) or {}

    try:
        existing = workflow_store.get_workflow(user_id, workflow_id)
        if not existing:
            return _err("Workflow not found", 404)

        # Merge: only update fields that were provided
        update = {
            "id":     workflow_id,
            "name":   body.get("name", existing["name"]),
            "status": body.get("status", existing["status"]),
            "graph":  body.get("graph", existing["graph"]),
        }

        workflow_store.save_workflow(user_id, update)
        workflow = workflow_store.get_workflow(user_id, workflow_id)
        return _ok({"workflow": workflow})

    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error(f"[/api/workflows/{workflow_id} PUT] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


@_wf_bp.route("/api/workflows/<workflow_id>", methods=["DELETE"])
@require_auth
def delete_workflow(workflow_id: str):
    """Delete a workflow by ID."""
    user_id = get_current_user_id()
    try:
        workflow_store.delete_workflow(user_id, workflow_id)
        return _ok({"deleted": workflow_id})
    except ValueError as e:
        return _err(str(e), 404)
    except Exception as e:
        logger.error(f"[/api/workflows/{workflow_id} DELETE] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


# ═══════════════════════════════════════════════════
# WORKFLOW EXECUTION
# ═══════════════════════════════════════════════════

@_wf_bp.route("/api/workflows/<workflow_id>/run", methods=["POST"])
@require_auth
def run_workflow(workflow_id: str):
    """
    Execute a workflow.
    Body: { "trigger_data": {} }  (optional)

    Runs synchronously and returns the full run result.
    For long-running workflows, consider running in a background thread
    and polling /runs/<run_id>.
    """
    user_id = get_current_user_id()
    body = request.get_json(silent=True) or {}
    trigger_data = body.get("trigger_data", {})

    try:
        # Verify workflow exists before running
        workflow = workflow_store.get_workflow(user_id, workflow_id)
        if not workflow:
            return _err("Workflow not found", 404)

        result = workflow_engine.run_workflow(user_id, workflow_id, trigger_data=trigger_data)
        return _ok({"run": result})

    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.error(f"[/api/workflows/{workflow_id}/run] {e}\n{traceback.format_exc()}")
        return _err(f"Workflow execution failed: {e}", 500)


@_wf_bp.route("/api/workflows/<workflow_id>/runs", methods=["GET"])
@require_auth
def list_runs(workflow_id: str):
    """List run history for a workflow, newest first."""
    user_id = get_current_user_id()
    try:
        runs = workflow_engine.list_runs(user_id, workflow_id)
        return _ok({"runs": runs, "count": len(runs)})
    except Exception as e:
        logger.error(f"[/api/workflows/{workflow_id}/runs] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


@_wf_bp.route("/api/workflows/<workflow_id>/runs/<run_id>", methods=["GET"])
@require_auth
def get_run(workflow_id: str, run_id: str):
    """Get a single run result."""
    user_id = get_current_user_id()
    try:
        run = workflow_engine.get_run(user_id, run_id)
        if not run:
            return _err("Run not found", 404)
        if run.get("workflow_id") != workflow_id:
            return _err("Run does not belong to this workflow", 404)
        return _ok({"run": run})
    except Exception as e:
        logger.error(f"[/api/workflows/{workflow_id}/runs/{run_id}] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


# ═══════════════════════════════════════════════════
# NODE LIBRARY
# ═══════════════════════════════════════════════════

@_wf_bp.route("/api/nodes", methods=["GET"])
@require_auth
def list_nodes():
    """
    List all available node definitions from the node library.
    Used by the frontend workflow editor to populate the node palette.
    """
    try:
        definitions = node_library.list_node_definitions()
        return _ok({"nodes": definitions, "count": len(definitions)})
    except Exception as e:
        logger.error(f"[/api/nodes] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


# ═══════════════════════════════════════════════════
# DUPLICATE
# ═══════════════════════════════════════════════════

@_wf_bp.route("/api/workflows/<workflow_id>/duplicate", methods=["POST"])
@require_auth
def duplicate_workflow(workflow_id: str):
    """Duplicate a workflow. Returns the new workflow."""
    user_id = get_current_user_id()
    try:
        new_id = workflow_store.duplicate_workflow(user_id, workflow_id)
        new_workflow = workflow_store.get_workflow(user_id, new_id)
        return _ok({"workflow": new_workflow}), 201
    except ValueError as e:
        return _err(str(e), 404)
    except Exception as e:
        logger.error(f"[/api/workflows/{workflow_id}/duplicate] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


# ═══════════════════════════════════════════════════
# CONVERSATION MEMORY DELETE
# ═══════════════════════════════════════════════════

@_wf_bp.route("/api/conversations/<conversation_id>/memory", methods=["DELETE"])
@require_auth
def delete_conversation_memory(conversation_id: str):
    """
    Deletes every knowledge node/edge/vector the AI learned from this chat.
    Wire this to the frontend's existing "delete chat" action so deleting a
    chat also erases what it taught the AI about the user.
    """
    user_id = get_current_user_id()
    try:
        deleted = kdb.delete_conversation_memory(user_id, conversation_id)
        return _ok({"conversation_id": conversation_id, "nodes_deleted": deleted})
    except Exception as e:
        logger.error(f"[/api/conversations/{conversation_id}/memory] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


# ═══════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════

def register_workflow_routes(app):
    """Call this in app.py after creating the Flask app."""
    app.register_blueprint(_wf_bp)
    logger.info("[Workflow] Routes registered under /api/workflows + /api/nodes")
