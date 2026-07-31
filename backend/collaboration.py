"""
collaboration.py — Xoltra Shared Workspace & Collaboration System

Features:
- Paid users can share workspaces by email invitation
- Non-users get one-time access links to the main user's workspace
- Collaborators can use the owner's tokens (with permission)
- Direct GitHub commits from shared workspace (manual folder commits)
- Git change auto-detection → auto-add to project file
- GitHub URL registration + collaborator management
"""
import os
import re
import json
import uuid
import hashlib
import secrets
import logging
import subprocess
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from flask import Blueprint, request, jsonify

import knowledge_db as kdb
from auth import require_auth, get_current_user_id
import subscription_manager as sm

logger = logging.getLogger(__name__)

collab_bp = Blueprint("collaboration", __name__, url_prefix="/api/collaboration")

_tables_created = False
GIT_BIN = shutil.which("git")

# ── Schema ────────────────────────────────────────────────

def init_collab_tables():
    global _tables_created
    if _tables_created:
        return
    conn = kdb._get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS shared_workspaces (
            id              TEXT PRIMARY KEY,
            owner_id        TEXT NOT NULL,
            name            TEXT NOT NULL,
            github_url      TEXT,
            github_collaborator TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workspace_members (
            id              TEXT PRIMARY KEY,
            workspace_id    TEXT NOT NULL,
            user_id         TEXT,           -- NULL for non-user invitees
            email           TEXT,
            role            TEXT NOT NULL DEFAULT 'editor',  -- owner, editor, viewer
            can_use_tokens  INTEGER DEFAULT 0,
            can_commit      INTEGER DEFAULT 0,
            invite_link     TEXT UNIQUE,
            link_expires_at TEXT,
            status          TEXT DEFAULT 'pending',  -- pending, active, revoked
            joined_at       TEXT,
            created_at      TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workspace_commits (
            id              TEXT PRIMARY KEY,
            workspace_id    TEXT NOT NULL,
            member_id       TEXT,
            folder_path     TEXT NOT NULL,
            commit_hash     TEXT,
            commit_message  TEXT,
            file_count      INTEGER DEFAULT 0,
            created_at      TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS git_watchers (
            id              TEXT PRIMARY KEY,
            workspace_id    TEXT NOT NULL,
            repo_path       TEXT NOT NULL,
            last_checked    TEXT,
            last_commit     TEXT,
            auto_push       INTEGER DEFAULT 1,
            created_at      TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ws_owner ON shared_workspaces(owner_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ws_member ON workspace_members(workspace_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ws_member_user ON workspace_members(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ws_invite ON workspace_members(invite_link)")
    conn.commit()
    _tables_created = True
    logger.info("[Collaboration] Tables initialized")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


def _ok(data: dict):
    return jsonify({"success": True, **data})


# ── Workspace CRUD ────────────────────────────────────────

@collab_bp.route("/workspaces", methods=["POST"])
@require_auth
def create_workspace():
    init_collab_tables()
    user_id = get_current_user_id()
    if not sm.check_permission(user_id, "workflow_builder"):
        return _err("Shared workspaces require a paid plan", 403)

    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return _err("name is required")

    ws_id = str(uuid.uuid4())
    now = _now()
    conn = kdb._get_conn()
    conn.execute(
        "INSERT INTO shared_workspaces (id, owner_id, name, github_url, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (ws_id, user_id, name, (body.get("github_url") or "").strip() or None, now, now)
    )
    # Owner is auto-added as member
    owner_mid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO workspace_members (id, workspace_id, user_id, email, role, can_use_tokens, can_commit, status, joined_at, created_at) VALUES (?, ?, ?, ?, 'owner', 1, 1, 'active', ?, ?)",
        (owner_mid, ws_id, user_id, "", now, now)
    )
    conn.commit()
    return _ok({"workspace": {"id": ws_id, "name": name, "owner_id": user_id, "created_at": now}}), 201


@collab_bp.route("/workspaces", methods=["GET"])
@require_auth
def list_workspaces():
    init_collab_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()
    rows = conn.execute(
        """SELECT sw.*, wm.role FROM shared_workspaces sw
           JOIN workspace_members wm ON sw.id = wm.workspace_id
           WHERE wm.user_id = ? AND wm.status = 'active'
           ORDER BY sw.updated_at DESC""",
        (user_id,)
    ).fetchall()
    return _ok({"workspaces": [dict(r) for r in rows]})


@collab_bp.route("/workspaces/<workspace_id>", methods=["GET"])
@require_auth
def get_workspace(workspace_id: str):
    init_collab_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()
    ws = conn.execute("SELECT * FROM shared_workspaces WHERE id = ?", (workspace_id,)).fetchone()
    if not ws:
        return _err("Workspace not found", 404)
    ws = dict(ws)

    # Check membership
    member = conn.execute(
        "SELECT * FROM workspace_members WHERE workspace_id = ? AND user_id = ? AND status = 'active'",
        (workspace_id, user_id)
    ).fetchone()
    if not member and ws["owner_id"] != user_id:
        return _err("Not a member of this workspace", 403)

    members = [dict(r) for r in conn.execute(
        "SELECT id, user_id, email, role, can_use_tokens, can_commit, status, joined_at FROM workspace_members WHERE workspace_id = ?",
        (workspace_id,)
    ).fetchall()]

    commits = [dict(r) for r in conn.execute(
        "SELECT * FROM workspace_commits WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 50",
        (workspace_id,)
    ).fetchall()]

    return _ok({"workspace": ws, "members": members, "commits": commits})


# ── Invitations ───────────────────────────────────────────

@collab_bp.route("/workspaces/<workspace_id>/invite", methods=["POST"])
@require_auth
def invite_member(workspace_id: str):
    init_collab_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()

    ws = conn.execute("SELECT * FROM shared_workspaces WHERE id = ? AND owner_id = ?",
                      (workspace_id, user_id)).fetchone()
    if not ws:
        return _err("Workspace not found or not owner", 404)

    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    can_use_tokens = bool(body.get("can_use_tokens", False))
    can_commit = bool(body.get("can_commit", True))

    if not email:
        return _err("email is required")

    # Check if this email belongs to a registered user
    existing_user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()

    mid = str(uuid.uuid4())
    now = _now()

    if existing_user:
        # Paid user — direct invite
        conn.execute(
            "INSERT INTO workspace_members (id, workspace_id, user_id, email, role, can_use_tokens, can_commit, status, joined_at, created_at) VALUES (?, ?, ?, ?, 'editor', ?, ?, 'active', ?, ?)",
            (mid, workspace_id, existing_user["id"], email, int(can_use_tokens), int(can_commit), now, now)
        )
        conn.execute("UPDATE shared_workspaces SET updated_at = ? WHERE id = ?", (now, workspace_id))
        conn.commit()
        return _ok({"member_id": mid, "email": email, "status": "active", "type": "direct"})

    # Non-user: generate one-time link
    invite_token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    conn.execute(
        "INSERT INTO workspace_members (id, workspace_id, user_id, email, role, can_use_tokens, can_commit, invite_link, link_expires_at, status, created_at) VALUES (?, ?, NULL, ?, 'editor', ?, ?, ?, ?, 'pending', ?)",
        (mid, workspace_id, email, int(can_use_tokens), int(can_commit), invite_token, expires, now)
    )
    conn.execute("UPDATE shared_workspaces SET updated_at = ? WHERE id = ?", (now, workspace_id))
    conn.commit()

    invite_url = f"/api/collaboration/join/{invite_token}"
    return _ok({
        "member_id": mid,
        "email": email,
        "status": "pending",
        "invite_link": invite_token,
        "invite_url": invite_url,
        "expires_at": expires
    })


@collab_bp.route("/join/<invite_token>", methods=["GET"])
def join_via_link(invite_token: str):
    """One-time link for non-users to access the workspace."""
    init_collab_tables()
    conn = kdb._get_conn()
    member = conn.execute(
        "SELECT * FROM workspace_members WHERE invite_link = ? AND status = 'pending'",
        (invite_token,)
    ).fetchone()
    if not member:
        return _err("Invalid or expired invite link", 404)

    member = dict(member)
    if member["link_expires_at"] and member["link_expires_at"] < _now():
        return _err("Invite link has expired", 410)

    # Activate the membership
    now = _now()
    conn.execute(
        "UPDATE workspace_members SET status = 'active', joined_at = ? WHERE id = ?",
        (now, member["id"])
    )
    conn.execute("UPDATE shared_workspaces SET updated_at = ? WHERE id = ?",
                 (now, member["workspace_id"]))
    conn.commit()

    ws = conn.execute("SELECT * FROM shared_workspaces WHERE id = ?",
                      (member["workspace_id"],)).fetchone()

    return _ok({
        "workspace": dict(ws) if ws else None,
        "member": {
            "id": member["id"],
            "role": member["role"],
            "can_use_tokens": bool(member["can_use_tokens"]),
            "can_commit": bool(member["can_commit"]),
        }
    })


# ── Token Sharing ─────────────────────────────────────────

@collab_bp.route("/workspaces/<workspace_id>/tokens/use", methods=["POST"])
@require_auth
def use_owner_tokens(workspace_id: str):
    """Collaborator uses owner's tokens for an operation."""
    init_collab_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()

    member = conn.execute(
        "SELECT * FROM workspace_members WHERE workspace_id = ? AND user_id = ? AND status = 'active'",
        (workspace_id, user_id)
    ).fetchone()
    if not member:
        return _err("Not a member of this workspace", 403)
    if not member["can_use_tokens"]:
        return _err("Token sharing not enabled for this member", 403)

    ws = conn.execute("SELECT owner_id FROM shared_workspaces WHERE id = ?",
                      (workspace_id,)).fetchone()
    if not ws:
        return _err("Workspace not found", 404)

    body = request.get_json(silent=True) or {}
    tokens_needed = int(body.get("tokens", 0))
    if tokens_needed <= 0:
        return _err("tokens must be positive")

    # Check owner has enough tokens
    owner_usage = sm.get_usage_summary(ws["owner_id"])
    if owner_usage["tokens_remaining"] is not None and owner_usage["tokens_remaining"] < tokens_needed:
        return _err("Owner has insufficient tokens", 402)

    # Deduct from owner, record as shared usage
    sm.deduct_usage(ws["owner_id"], tokens_needed, model_name="shared_workspace",
                    agent_name=f"collaborator:{user_id}", execution_id=workspace_id)

    return _ok({
        "tokens_granted": tokens_needed,
        "owner_remaining": sm.get_remaining_tokens(ws["owner_id"])
    })


# ── Git Integration ───────────────────────────────────────

@collab_bp.route("/workspaces/<workspace_id>/github/register", methods=["POST"])
@require_auth
def register_github(workspace_id: str):
    """Register a GitHub repo URL and collaborator for the workspace."""
    init_collab_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()

    ws = conn.execute("SELECT * FROM shared_workspaces WHERE id = ? AND owner_id = ?",
                      (workspace_id, user_id)).fetchone()
    if not ws:
        return _err("Workspace not found or not owner", 404)

    body = request.get_json(silent=True) or {}
    github_url = (body.get("github_url") or "").strip()
    collaborator = (body.get("github_collaborator") or "").strip()

    if not github_url:
        return _err("github_url is required")

    GITHUB_RE = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+(\.git)?/?$")
    if not GITHUB_RE.match(github_url):
        return _err("Invalid GitHub URL format")

    now = _now()
    conn.execute(
        "UPDATE shared_workspaces SET github_url = ?, github_collaborator = ?, updated_at = ? WHERE id = ?",
        (github_url, collaborator or None, now, workspace_id)
    )
    conn.commit()

    # Set up git watcher for auto-commit
    watcher_id = str(uuid.uuid4())
    conn.execute(
        "INSERT OR REPLACE INTO git_watchers (id, workspace_id, repo_path, auto_push, created_at) VALUES (?, ?, ?, 1, ?)",
        (watcher_id, workspace_id, github_url, now)
    )
    conn.commit()

    return _ok({"workspace_id": workspace_id, "github_url": github_url, "collaborator": collaborator})


@collab_bp.route("/workspaces/<workspace_id>/github/commit", methods=["POST"])
@require_auth
def commit_to_workspace(workspace_id: str):
    """Commit changes from a shared folder to GitHub."""
    init_collab_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()

    member = conn.execute(
        "SELECT * FROM workspace_members WHERE workspace_id = ? AND user_id = ? AND status = 'active'",
        (workspace_id, user_id)
    ).fetchone()
    if not member:
        return _err("Not a member of this workspace", 403)
    if not member["can_commit"]:
        return _err("Commit permission not granted", 403)

    ws = conn.execute("SELECT * FROM shared_workspaces WHERE id = ?", (workspace_id,)).fetchone()
    if not ws or not ws["github_url"]:
        return _err("No GitHub repo registered for this workspace", 400)

    body = request.get_json(silent=True) or {}
    folder_path = (body.get("folder_path") or "").strip()
    message = (body.get("message") or f"Update from collaborator {user_id}").strip()

    if not folder_path:
        return _err("folder_path is required")

    # Clone repo, apply changes, commit, push
    if GIT_BIN is None:
        return _err("git not installed on host", 501)

    scratch = tempfile.mkdtemp(prefix=f"xoltra-collab-{workspace_id}-")
    try:
        subprocess.run(
            [GIT_BIN, "clone", "--depth", "1", ws["github_url"], scratch],
            check=True, timeout=60, capture_output=True, text=True
        )

        # Apply changes from the member's folder
        target = os.path.join(scratch, folder_path)
        os.makedirs(target, exist_ok=True)

        # If content provided, write it
        content = body.get("content")
        if content:
            file_name = body.get("file_name", "changes.txt")
            with open(os.path.join(target, file_name), "w", encoding="utf-8") as f:
                f.write(content)

        # Git add, commit, push
        subprocess.run([GIT_BIN, "add", "."], cwd=scratch, check=True, capture_output=True, text=True)
        result = subprocess.run(
            [GIT_BIN, "commit", "-m", message],
            cwd=scratch, capture_output=True, text=True
        )
        commit_hash = None
        if result.returncode == 0:
            log_result = subprocess.run(
                [GIT_BIN, "log", "-1", "--format=%H"],
                cwd=scratch, capture_output=True, text=True
            )
            commit_hash = log_result.stdout.strip()

        subprocess.run(
            [GIT_BIN, "push", "origin", "HEAD"],
            cwd=scratch, check=True, timeout=30, capture_output=True, text=True
        )

        # Record commit
        cid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO workspace_commits (id, workspace_id, member_id, folder_path, commit_hash, message, file_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, workspace_id, member["id"], folder_path, commit_hash, message, 1 if content else 0, _now())
        )
        conn.execute("UPDATE shared_workspaces SET updated_at = ? WHERE id = ?", (_now(), workspace_id))
        conn.commit()

        return _ok({"commit_id": cid, "hash": commit_hash, "folder": folder_path})
    except subprocess.CalledProcessError as e:
        return _err(f"Git operation failed: {e.stderr[:300]}", 502)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ── Git Auto-Watcher ──────────────────────────────────────

@collab_bp.route("/workspaces/<workspace_id>/git/check", methods=["POST"])
@require_auth
def check_git_changes(workspace_id: str):
    """Poll for git changes and auto-add to project file."""
    init_collab_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()

    ws = conn.execute("SELECT * FROM shared_workspaces WHERE id = ?", (workspace_id,)).fetchone()
    if not ws:
        return _err("Workspace not found", 404)

    watcher = conn.execute(
        "SELECT * FROM git_watchers WHERE workspace_id = ?", (workspace_id,)
    ).fetchone()
    if not watcher or not ws["github_url"]:
        return _ok({"changes": [], "message": "No watcher configured"})

    if GIT_BIN is None:
        return _err("git not installed", 501)

    scratch = tempfile.mkdtemp(prefix=f"xoltra-watch-{workspace_id}-")
    try:
        subprocess.run(
            [GIT_BIN, "clone", "--depth", "1", ws["github_url"], scratch],
            check=True, timeout=60, capture_output=True, text=True
        )

        # Get latest commit
        result = subprocess.run(
            [GIT_BIN, "log", "-1", "--format=%H"],
            cwd=scratch, capture_output=True, text=True
        )
        latest_hash = result.stdout.strip()

        changes = []
        if watcher["last_commit"] and watcher["last_commit"] != latest_hash:
            # Get diff since last check
            diff_result = subprocess.run(
                [GIT_BIN, "diff", "--name-only", watcher["last_commit"], latest_hash],
                cwd=scratch, capture_output=True, text=True
            )
            changes = [f for f in diff_result.stdout.strip().split("\n") if f]

            # Auto-add to project file
            if changes:
                _sync_changes_to_project(workspace_id, ws["owner_id"], changes, latest_hash)

        # Update watcher
        conn.execute(
            "UPDATE git_watchers SET last_checked = ?, last_commit = ? WHERE id = ?",
            (_now(), latest_hash, watcher["id"])
        )
        conn.commit()

        return _ok({"changes": changes, "latest_hash": latest_hash, "count": len(changes)})
    except subprocess.CalledProcessError as e:
        return _err(f"Git check failed: {e.stderr[:300]}", 502)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _sync_changes_to_project(workspace_id: str, owner_id: str, changed_files: List[str], commit_hash: str):
    """Auto-add git changes to the project's knowledge base."""
    try:
        import projects as proj
        proj.init_project_tables()
        conn = kdb._get_conn()

        # Find or create a project for this workspace
        proj_row = conn.execute(
            "SELECT id FROM projects WHERE user_id = ? AND name LIKE ?",
            (owner_id, f"%workspace:{workspace_id}%")
        ).fetchone()

        if not proj_row:
            # Create auto-project
            pid = str(uuid.uuid4())
            now = _now()
            conn.execute(
                "INSERT INTO projects (id, user_id, name, goals, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (pid, owner_id, f"Workspace Auto-Sync: {workspace_id}",
                 f"Auto-tracked changes from shared workspace. Last commit: {commit_hash}", now, now)
            )
            conn.commit()
            proj_row = {"id": pid}

        # Append digest
        digest_row = conn.execute(
            "SELECT conversation_digests FROM project_cache WHERE project_id = ?",
            (proj_row["id"],)
        ).fetchone()
        digests = json.loads(digest_row["conversation_digests"]) if digest_row else []
        digests.append({
            "conversation_id": f"git-{commit_hash[:8]}",
            "summary": f"Git changes: {', '.join(changed_files[:10])}",
            "created_at": _now(),
        })
        digests = digests[-50:]

        conn.execute("""
            INSERT INTO project_cache (project_id, structure_summary, key_docs_summary, conversation_digests, updated_at)
            VALUES (?, '', '', ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                conversation_digests = excluded.conversation_digests,
                updated_at = excluded.updated_at
        """, (proj_row["id"], json.dumps(digests), _now()))
        conn.commit()
        logger.info(f"[Collaboration] Synced {len(changed_files)} git changes to project {proj_row['id']}")
    except Exception as e:
        logger.error(f"[Collaboration] Git sync failed: {e}")


# ── Token Permission Management ───────────────────────────

@collab_bp.route("/workspaces/<workspace_id>/members/<member_id>/permissions", methods=["PUT"])
@require_auth
def update_member_permissions(workspace_id: str, member_id: str):
    init_collab_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()

    ws = conn.execute("SELECT * FROM shared_workspaces WHERE id = ? AND owner_id = ?",
                      (workspace_id, user_id)).fetchone()
    if not ws:
        return _err("Workspace not found or not owner", 404)

    body = request.get_json(silent=True) or {}
    updates = {}
    if "can_use_tokens" in body:
        updates["can_use_tokens"] = int(bool(body["can_use_tokens"]))
    if "can_commit" in body:
        updates["can_commit"] = int(bool(body["can_commit"]))
    if "role" in body and body["role"] in ("editor", "viewer"):
        updates["role"] = body["role"]

    if not updates:
        return _err("No valid permission fields provided")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [member_id, workspace_id]
    conn.execute(
        f"UPDATE workspace_members SET {set_clause} WHERE id = ? AND workspace_id = ?",
        values
    )
    conn.execute("UPDATE shared_workspaces SET updated_at = ? WHERE id = ?", (_now(), workspace_id))
    conn.commit()

    return _ok({"member_id": member_id, "updated": updates})


@collab_bp.route("/workspaces/<workspace_id>/members/<member_id>", methods=["DELETE"])
@require_auth
def remove_member(workspace_id: str, member_id: str):
    init_collab_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()

    ws = conn.execute("SELECT * FROM shared_workspaces WHERE id = ? AND owner_id = ?",
                      (workspace_id, user_id)).fetchone()
    if not ws:
        return _err("Workspace not found or not owner", 404)

    conn.execute("UPDATE workspace_members SET status = 'revoked' WHERE id = ? AND workspace_id = ?",
                 (member_id, workspace_id))
    conn.execute("UPDATE shared_workspaces SET updated_at = ? WHERE id = ?", (_now(), workspace_id))
    conn.commit()
    return _ok({"removed": member_id})


def register_collaboration_routes(app):
    app.register_blueprint(collab_bp)
    logger.info("[Collaboration] Routes registered under /api/collaboration")