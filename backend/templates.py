"""
templates.py — Internal workflow template gallery (per-user, not public).

Save any workflow's graph as a named template, list your templates,
instantiate one into a brand-new draft workflow, delete when done.
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional

from flask import Blueprint, request, jsonify

import knowledge_db as kdb
import workflow_store
from auth import require_auth, get_current_user_id

logger = logging.getLogger(__name__)

templates_bp = Blueprint("templates", __name__, url_prefix="/api/templates")

_tables_created = False


def init_template_tables():
    global _tables_created
    if _tables_created:
        return
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_templates (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            name        TEXT NOT NULL,
            description TEXT,
            graph       TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_templates_user ON workflow_templates(user_id)")
    conn.commit()
    _tables_created = True


def _row_to_dict(row) -> Dict:
    return {
        "id": row["id"], "name": row["name"], "description": row["description"],
        "graph": json.loads(row["graph"]), "created_at": row["created_at"],
    }


def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


def _ok(data: dict):
    return jsonify({"success": True, **data})


@templates_bp.route("", methods=["POST"])
@require_auth
def save_template():
    """Body: { workflow_id } or { name, graph } directly."""
    init_template_tables()
    user_id = get_current_user_id()
    body = request.get_json(silent=True) or {}

    if body.get("workflow_id"):
        wf = workflow_store.get_workflow(user_id, body["workflow_id"])
        if not wf:
            return _err("Workflow not found", 404)
        name = body.get("name") or f"{wf['name']} (Template)"
        graph = wf["graph"]
    else:
        name = (body.get("name") or "").strip()
        graph = body.get("graph")
        if not name or not graph:
            return _err("name and graph (or workflow_id) required")

    template_id = str(uuid.uuid4())
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO workflow_templates (id, user_id, name, description, graph, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (template_id, user_id, name, body.get("description", ""), json.dumps(graph), datetime.utcnow().isoformat())
    )
    conn.commit()
    return _ok({"template_id": template_id}), 201


@templates_bp.route("", methods=["GET"])
@require_auth
def list_templates():
    init_template_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workflow_templates WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    return _ok({"templates": [_row_to_dict(r) for r in cursor.fetchall()]})


@templates_bp.route("/<template_id>/instantiate", methods=["POST"])
@require_auth
def instantiate_template(template_id: str):
    """Creates a new draft workflow from the template's saved graph."""
    init_template_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workflow_templates WHERE id = ? AND user_id = ?", (template_id, user_id))
    row = cursor.fetchone()
    if not row:
        return _err("Template not found", 404)

    tpl = _row_to_dict(row)
    body = request.get_json(silent=True) or {}
    new_name = body.get("name") or tpl["name"]

    workflow_id = workflow_store.save_workflow(user_id, {
        "name": new_name, "status": "draft", "graph": tpl["graph"],
    })
    workflow = workflow_store.get_workflow(user_id, workflow_id)
    return _ok({"workflow": workflow}), 201


@templates_bp.route("/<template_id>", methods=["DELETE"])
@require_auth
def delete_template(template_id: str):
    init_template_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM workflow_templates WHERE id = ? AND user_id = ?", (template_id, user_id))
    conn.commit()
    if cursor.rowcount == 0:
        return _err("Template not found", 404)
    return _ok({"deleted": template_id})


def register_template_routes(app):
    app.register_blueprint(templates_bp)
    logger.info("[Templates] Routes registered under /api/templates")
