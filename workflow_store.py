"""
workflow_store.py — Xoltra Workflow Persistence Layer

Persists workflow definitions (nodes + edges graph) to the same SQLite database
used by knowledge_db.py. Reuses the thread-local connection pattern and DB_PATH
so there is only one database file for the entire system.

A workflow document:
{
    "id":         "uuid",
    "name":       "My Workflow",
    "status":     "draft" | "published",
    "created_at": "ISO-8601",
    "updated_at": "ISO-8601",
    "graph": {
        "nodes": [ { "id", "type", "label", "params", "position" }, ... ],
        "edges": [ { "id", "source", "target", "source_port", "target_port" }, ... ]
    }
}

Functions:
    save_workflow()      — upsert, returns workflow_id
    get_workflow()       — fetch by id
    list_workflows()     — list with optional status filter
    delete_workflow()    — hard delete
    duplicate_workflow() — deep copy with new id + " (Copy)" name
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional

import knowledge_db as kdb

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# SCHEMA — called once at import time via init_workflow_tables()
# ═══════════════════════════════════════════════════

_tables_created = False


def init_workflow_tables():
    """
    Create the workflows table in the shared SQLite database.
    Safe to call multiple times — idempotent.
    Must be called after kdb.init_storage().
    """
    global _tables_created
    if _tables_created:
        return

    conn = kdb._get_conn()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workflows (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        status      TEXT NOT NULL DEFAULT 'draft',
        graph       TEXT NOT NULL DEFAULT '{"nodes":[],"edges":[]}',
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status)")
    conn.commit()
    _tables_created = True
    logger.info("[WorkflowStore] Tables initialized")


# ═══════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════

def save_workflow(workflow: dict) -> str:
    """
    Upsert a workflow definition. Returns workflow_id.

    If workflow['id'] exists in the DB, update it.
    If workflow['id'] is missing or not found, insert a new row.

    Required keys: 'name', 'graph'.
    Optional keys: 'id', 'status', 'created_at', 'updated_at'.
    """
    init_workflow_tables()

    workflow_id = workflow.get("id") or str(uuid.uuid4())
    name        = workflow.get("name")
    status      = workflow.get("status", "draft")
    graph       = workflow.get("graph", {"nodes": [], "edges": []})
    now         = datetime.utcnow().isoformat()

    if not name:
        raise ValueError("Workflow 'name' is required")
    if status not in ("draft", "published"):
        raise ValueError(f"Invalid workflow status: '{status}'. Must be 'draft' or 'published'")
    if not isinstance(graph, dict):
        raise ValueError("Workflow 'graph' must be a dict with 'nodes' and 'edges'")

    conn   = kdb._get_conn()
    cursor = conn.cursor()

    # Check if this workflow already exists
    cursor.execute("SELECT id, created_at FROM workflows WHERE id = ?", (workflow_id,))
    existing = cursor.fetchone()

    if existing:
        # Update
        cursor.execute("""
            UPDATE workflows
            SET name = ?, status = ?, graph = ?, updated_at = ?
            WHERE id = ?
        """, (name, status, json.dumps(graph), now, workflow_id))
        logger.debug(f"[WorkflowStore] Updated workflow: {workflow_id[:8]}")
    else:
        # Insert
        created_at = workflow.get("created_at", now)
        cursor.execute("""
            INSERT INTO workflows (id, name, status, graph, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (workflow_id, name, status, json.dumps(graph), created_at, now))
        logger.debug(f"[WorkflowStore] Created workflow: {workflow_id[:8]}")

    conn.commit()
    return workflow_id


def get_workflow(workflow_id: str) -> Optional[Dict]:
    """
    Retrieve a single workflow by ID.
    Returns None if not found.
    """
    init_workflow_tables()

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
    row = cursor.fetchone()

    if not row:
        return None

    return _row_to_dict(row)


def list_workflows(status: str = None) -> List[Dict]:
    """
    List all workflows, optionally filtered by status ('draft' or 'published').
    Returns newest-first.
    """
    init_workflow_tables()

    conn   = kdb._get_conn()
    cursor = conn.cursor()

    if status:
        if status not in ("draft", "published"):
            raise ValueError(f"Invalid status filter: '{status}'")
        cursor.execute(
            "SELECT * FROM workflows WHERE status = ? ORDER BY updated_at DESC",
            (status,)
        )
    else:
        cursor.execute("SELECT * FROM workflows ORDER BY updated_at DESC")

    return [_row_to_dict(row) for row in cursor.fetchall()]


def delete_workflow(workflow_id: str):
    """
    Hard-delete a workflow by ID.
    Raises ValueError if the workflow does not exist.
    """
    init_workflow_tables()

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
    conn.commit()

    if cursor.rowcount == 0:
        raise ValueError(f"Workflow not found: {workflow_id}")

    logger.info(f"[WorkflowStore] Deleted workflow: {workflow_id[:8]}")


def duplicate_workflow(workflow_id: str) -> str:
    """
    Deep-copy a workflow with a new ID and ' (Copy)' appended to the name.
    Returns the new workflow_id.
    Raises ValueError if the source workflow does not exist.
    """
    source = get_workflow(workflow_id)
    if not source:
        raise ValueError(f"Cannot duplicate — workflow not found: {workflow_id}")

    new_workflow = {
        "name":   source["name"] + " (Copy)",
        "status": "draft",
        "graph":  source["graph"],
    }
    return save_workflow(new_workflow)


# ═══════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════

def _row_to_dict(row) -> Dict:
    """Convert a sqlite3.Row to a clean dict with parsed JSON graph."""
    return {
        "id":         row["id"],
        "name":       row["name"],
        "status":     row["status"],
        "graph":      json.loads(row["graph"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
