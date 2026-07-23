"""
teams.py, Tier-2 readiness: minimal orgs, role-based access, SSO groundwork.

Xoltra today has no concept of a team at all, every account is a single
independent owner. "RBAC" only means something once there's more than one
person who can hold a different role, so this adds the smallest org model
that makes that real, not a full enterprise team-management suite:

  - Every user gets a personal org, auto-provisioned on first request to
    any /api/orgs/* route (lazy, existing accounts need no migration).
  - Owners/admins can invite others via a short code (same pattern as
    referrals.py's codes, reused deliberately for consistency).
  - Three roles: owner (one per org, can't be removed, can change roles),
    admin (can invite, can export audit), member (can use the org, no
    admin actions).
  - SSO groundwork means exactly that: a place to declare intent
    (provider, config) per org, gated by role. It does NOT implement a
    real SAML/OIDC handshake, that's a real integration decision
    (WorkOS/Auth0/Okta, or build it directly) that needs to be made
    deliberately, not guessed at here. The route exists so the frontend
    and billing/plan-gating around it can be built without waiting on
    that decision.
"""

import logging
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Optional

from flask import Blueprint, request, jsonify

import knowledge_db as kdb
from auth import require_auth, get_current_user_id

logger = logging.getLogger(__name__)

teams_bp = Blueprint("teams", __name__, url_prefix="/api/orgs")

_tables_created = False
_CODE_ALPHABET = string.ascii_uppercase + string.digits
_ROLES = ("owner", "admin", "member")
_ADMIN_ROLES = ("owner", "admin")


def init_team_tables():
    global _tables_created
    if _tables_created:
        return
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            created_at    TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organization_members (
            org_id    TEXT NOT NULL,
            user_id   TEXT NOT NULL,
            role      TEXT NOT NULL DEFAULT 'member',
            joined_at TEXT NOT NULL,
            PRIMARY KEY (org_id, user_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_org_members_user ON organization_members(user_id)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS org_invites (
            code       TEXT PRIMARY KEY,
            org_id     TEXT NOT NULL,
            role       TEXT NOT NULL DEFAULT 'member',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS org_sso_config (
            org_id       TEXT PRIMARY KEY,
            provider     TEXT,
            enabled      INTEGER NOT NULL DEFAULT 0,
            config_json  TEXT NOT NULL DEFAULT '{}',
            updated_at   TEXT NOT NULL
        )
    """)
    conn.commit()
    _tables_created = True


def ensure_personal_org(user_id: str) -> str:
    """Every user has at least one org, themselves, as owner. Lazy-created."""
    init_team_tables()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT org_id FROM organization_members WHERE user_id = ? ORDER BY joined_at ASC LIMIT 1",
        (user_id,)
    )
    row = cursor.fetchone()
    if row:
        return row["org_id"]

    org_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO organizations (id, name, owner_user_id, created_at) VALUES (?, ?, ?, ?)",
        (org_id, "My Organization", user_id, now)
    )
    cursor.execute(
        "INSERT INTO organization_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
        (org_id, user_id, now)
    )
    conn.commit()
    return org_id


def get_user_role(org_id: str, user_id: str) -> Optional[str]:
    init_team_tables()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role FROM organization_members WHERE org_id = ? AND user_id = ?", (org_id, user_id)
    )
    row = cursor.fetchone()
    return row["role"] if row else None


def list_user_orgs(user_id: str) -> list:
    init_team_tables()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT o.id, o.name, m.role FROM organizations o
        JOIN organization_members m ON m.org_id = o.id
        WHERE m.user_id = ?
        ORDER BY m.joined_at ASC
    """, (user_id,))
    return [dict(r) for r in cursor.fetchall()]


def list_members(org_id: str) -> list:
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.user_id, m.role, m.joined_at, u.email FROM organization_members m
        JOIN users u ON u.id = m.user_id
        WHERE m.org_id = ?
        ORDER BY m.joined_at ASC
    """, (org_id,))
    return [dict(r) for r in cursor.fetchall()]


def create_invite(org_id: str, role: str, created_by: str) -> str:
    if role not in _ROLES:
        raise ValueError(f"role must be one of {_ROLES}")
    init_team_tables()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    for _ in range(5):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        cursor.execute("SELECT 1 FROM org_invites WHERE code = ?", (code,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO org_invites (code, org_id, role, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (code, org_id, role, created_by, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()
            return code
    raise RuntimeError("Could not generate a unique invite code after 5 attempts")


def redeem_invite(code: str, user_id: str) -> Optional[str]:
    """Returns the org_id joined, or None if the code is invalid."""
    init_team_tables()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT org_id, role FROM org_invites WHERE code = ?", (code.strip().upper(),))
    row = cursor.fetchone()
    if not row:
        return None

    org_id, role = row["org_id"], row["role"]
    cursor.execute(
        "INSERT OR IGNORE INTO organization_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
        (org_id, user_id, role, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    return org_id


# ─── Route guard ──────────────────────────────────────────────────────────

def require_org_role(*roles):
    """Decorator for routes with <org_id> in the URL. 403s if the current
    user isn't a member of that org, or isn't one of the given roles."""
    from functools import wraps

    def decorator(fn):
        @wraps(fn)
        def wrapper(org_id, *args, **kwargs):
            user_id = get_current_user_id()
            role = get_user_role(org_id, user_id)
            if role is None:
                return jsonify({"success": False, "error": "Not found"}), 404
            if roles and role not in roles:
                return jsonify({"success": False, "error": "Forbidden"}), 403
            return fn(org_id, *args, **kwargs)
        return wrapper
    return decorator


# ─── Routes ───────────────────────────────────────────────────────────────

def _ok(data: dict):
    return jsonify({"success": True, **data})


def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


@teams_bp.route("/me", methods=["GET"])
@require_auth
def route_my_orgs():
    user_id = get_current_user_id()
    ensure_personal_org(user_id)
    return _ok({"organizations": list_user_orgs(user_id)})


@teams_bp.route("/<org_id>/members", methods=["GET"])
@require_auth
@require_org_role()  # any member can see the roster
def route_members(org_id):
    return _ok({"members": list_members(org_id)})


@teams_bp.route("/<org_id>/invites", methods=["POST"])
@require_auth
@require_org_role(*_ADMIN_ROLES)
def route_create_invite(org_id):
    user_id = get_current_user_id()
    body = request.get_json(silent=True) or {}
    role = body.get("role", "member")
    if role not in _ROLES:
        return _err(f"role must be one of {_ROLES}")
    if role == "owner":
        return _err("Cannot invite someone directly as owner, invite as admin, then transfer ownership")
    try:
        code = create_invite(org_id, role, user_id)
        return _ok({"code": code}), 201
    except Exception as e:
        return _err(str(e), 500)


@teams_bp.route("/join", methods=["POST"])
@require_auth
def route_join():
    user_id = get_current_user_id()
    body = request.get_json(silent=True) or {}
    code = (body.get("code") or "").strip()
    if not code:
        return _err("code is required")
    org_id = redeem_invite(code, user_id)
    if not org_id:
        return _err("Invalid or expired invite code", 404)
    return _ok({"org_id": org_id})


@teams_bp.route("/<org_id>/members/<member_user_id>/role", methods=["PATCH"])
@require_auth
@require_org_role("owner")
def route_set_role(org_id, member_user_id):
    body = request.get_json(silent=True) or {}
    new_role = body.get("role")
    if new_role not in _ROLES:
        return _err(f"role must be one of {_ROLES}")

    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT owner_user_id FROM organizations WHERE id = ?", (org_id,))
    org = cursor.fetchone()
    if org and org["owner_user_id"] == member_user_id and new_role != "owner":
        return _err("Transfer ownership first, don't demote the current owner directly")

    cursor.execute(
        "UPDATE organization_members SET role = ? WHERE org_id = ? AND user_id = ?",
        (new_role, org_id, member_user_id)
    )
    conn.commit()
    return _ok({"org_id": org_id, "user_id": member_user_id, "role": new_role})


@teams_bp.route("/<org_id>/sso-config", methods=["GET"])
@require_auth
@require_org_role(*_ADMIN_ROLES)
def route_get_sso_config(org_id):
    init_team_tables()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT provider, enabled, config_json, updated_at FROM org_sso_config WHERE org_id = ?", (org_id,))
    row = cursor.fetchone()
    if not row:
        return _ok({"provider": None, "enabled": False, "config": {}})
    import json as _json
    return _ok({"provider": row["provider"], "enabled": bool(row["enabled"]),
                "config": _json.loads(row["config_json"]), "updated_at": row["updated_at"]})


@teams_bp.route("/<org_id>/sso-config", methods=["PUT"])
@require_auth
@require_org_role(*_ADMIN_ROLES)
def route_set_sso_config(org_id):
    """
    Declares SSO intent only, provider + config are stored, nothing here
    actually performs a SAML/OIDC handshake. Real SSO needs a provider
    decision (WorkOS is the common fast-path for a startup, direct SAML/
    OIDC is the DIY path) before there's anything to wire this up to.
    """
    import json as _json
    body = request.get_json(silent=True) or {}
    provider = body.get("provider")
    enabled = bool(body.get("enabled", False))
    config = body.get("config") or {}

    init_team_tables()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO org_sso_config (org_id, provider, enabled, config_json, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(org_id) DO UPDATE SET provider=excluded.provider, enabled=excluded.enabled,
            config_json=excluded.config_json, updated_at=excluded.updated_at
    """, (org_id, provider, 1 if enabled else 0, _json.dumps(config), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    return _ok({"provider": provider, "enabled": enabled})


@teams_bp.route("/<org_id>/audit-log/export", methods=["GET"])
@require_auth
@require_org_role(*_ADMIN_ROLES)
def route_export_audit_log(org_id):
    """
    Customer-facing audit export, distinct from admin_routes.py's
    X-Admin-Key-gated endpoint, which is Xoltra's own operator tool, not
    something a customer's org admin can reach. This is gated by org role
    instead: any admin/owner of THIS org can export THIS org's trail.
    """
    fmt = request.args.get("format", "json")
    member_ids = {m["user_id"] for m in list_members(org_id)}

    try:
        import node_library
        bridge, _ = node_library.get_bridge()
        entries = bridge.get_audit_log(n=10000, user_ids=member_ids)
    except Exception as e:
        return _err(f"Export failed: {e}", 500)

    if fmt == "csv":
        import csv, io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["timestamp", "user_id", "node_id", "node_name", "action", "outcome", "reason"])
        writer.writeheader()
        for e in entries:
            writer.writerow({k: e.get(k, "") for k in writer.fieldnames})
        from flask import Response
        return Response(
            buf.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=xoltra-audit-{org_id[:8]}.csv"}
        )

    return _ok({"entries": entries, "count": len(entries)})


def register_team_routes(app):
    app.register_blueprint(teams_bp)
    logger.info("[Teams] Routes registered under /api/orgs")
