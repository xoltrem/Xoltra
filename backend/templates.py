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
    # Marketplace v1: publish a template publicly, track category and
    # popularity. Existing rows default to is_public=0, private, unaffected.
    kdb._add_column_if_not_exists(cursor, "workflow_templates", "is_public", "INTEGER NOT NULL DEFAULT 0")
    kdb._add_column_if_not_exists(cursor, "workflow_templates", "category", "TEXT")
    kdb._add_column_if_not_exists(cursor, "workflow_templates", "use_count", "INTEGER NOT NULL DEFAULT 0")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_templates_public ON workflow_templates(is_public)")
    conn.commit()
    _tables_created = True


_ALLOWED_CATEGORIES = {"sales", "support", "marketing", "ops", "engineering", "personal", "other"}


def _row_to_dict(row, include_owner_fields: bool = True) -> Dict:
    d = {
        "id": row["id"], "name": row["name"], "description": row["description"],
        "graph": json.loads(row["graph"]), "created_at": row["created_at"],
        "is_public": bool(row["is_public"]), "category": row["category"],
        "use_count": row["use_count"],
    }
    if include_owner_fields:
        d["user_id"] = row["user_id"]
    return d


def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


def _ok(data: dict):
    return jsonify({"success": True, **data})


@templates_bp.route("", methods=["POST"])
@require_auth
def save_template():
    """Body: { workflow_id } or { name, graph } directly. Optional: category. Starts private."""
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

    category = body.get("category")
    if category and category not in _ALLOWED_CATEGORIES:
        return _err(f"category must be one of {sorted(_ALLOWED_CATEGORIES)}")

    template_id = str(uuid.uuid4())
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO workflow_templates (id, user_id, name, description, graph, created_at, category) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (template_id, user_id, name, body.get("description", ""), json.dumps(graph),
         datetime.utcnow().isoformat(), category)
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


@templates_bp.route("/<template_id>/publish", methods=["PATCH"])
@require_auth
def set_publish_state(template_id: str):
    """Body: { is_public: bool }. Owner-only — publishing someone else's template isn't a thing."""
    init_template_tables()
    user_id = get_current_user_id()
    body = request.get_json(silent=True) or {}
    if "is_public" not in body:
        return _err("is_public (bool) is required")

    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM workflow_templates WHERE id = ? AND user_id = ?", (template_id, user_id))
    if not cursor.fetchone():
        return _err("Template not found", 404)

    cursor.execute(
        "UPDATE workflow_templates SET is_public = ? WHERE id = ? AND user_id = ?",
        (1 if body["is_public"] else 0, template_id, user_id)
    )
    conn.commit()
    return _ok({"template_id": template_id, "is_public": bool(body["is_public"])})


@templates_bp.route("/public", methods=["GET"])
@require_auth
def list_public_templates():
    """
    Marketplace browse. Requires login (v1 scope — no unauthenticated public
    pages yet, see the import-onboarding patch's honesty pattern: this is a
    real limitation against the GTM plan's public-template-SEO ambition, not
    hidden). Query params: category (optional), q (optional, matches name).
    """
    init_template_tables()
    category = request.args.get("category")
    q = request.args.get("q", "").strip()

    sql = "SELECT * FROM workflow_templates WHERE is_public = 1"
    params: list = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if q:
        sql += " AND name LIKE ?"
        params.append(f"%{q}%")
    sql += " ORDER BY use_count DESC, created_at DESC LIMIT 100"

    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return _ok({"templates": [_row_to_dict(r, include_owner_fields=False) for r in cursor.fetchall()]})


@templates_bp.route("/<template_id>/use", methods=["POST"])
@require_auth
def use_template(template_id: str):
    """
    Instantiate ANY public template (or your own private one) into a new
    draft workflow. Distinct from /instantiate below, which stays owner-only
    for backward compatibility with existing frontend calls.
    """
    init_template_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM workflow_templates WHERE id = ? AND (is_public = 1 OR user_id = ?)",
        (template_id, user_id)
    )
    row = cursor.fetchone()
    if not row:
        return _err("Template not found or not public", 404)

    tpl = _row_to_dict(row)
    body = request.get_json(silent=True) or {}
    new_name = body.get("name") or tpl["name"]

    workflow_id = workflow_store.save_workflow(user_id, {
        "name": new_name, "status": "draft", "graph": tpl["graph"],
    })
    cursor.execute("UPDATE workflow_templates SET use_count = use_count + 1 WHERE id = ?", (template_id,))
    conn.commit()
    workflow = workflow_store.get_workflow(user_id, workflow_id)
    return _ok({"workflow": workflow}), 201


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
