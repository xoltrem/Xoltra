"""
admin_routes.py — Operator-only endpoints: backup health + disaster recovery.

Protected by ADMIN_KEY (X-Admin-Key header), separate from the normal user
JWT and from auth.py's service-to-service INTERNAL_SERVICE_KEY — this is a
human operator action, not a user request or a server-to-server handoff.
"""

import os
import logging

from flask import Blueprint, request, jsonify

import backup_service
import moderation

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

ADMIN_KEY = os.environ.get("ADMIN_KEY", "dev-admin-key-do-not-use-in-prod")


def _require_admin():
    return request.headers.get("X-Admin-Key") == ADMIN_KEY


def _ok(data: dict):
    return jsonify({"success": True, **data})


def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


@admin_bp.route("/backup-status", methods=["GET"])
def backup_status():
    """Last snapshot time/size, or why backups are disabled. No secrets returned."""
    if not _require_admin():
        return _err("Forbidden", 403)
    try:
        return _ok(backup_service.get_status())
    except Exception as e:
        logger.error(f"[Admin] backup-status failed: {e}")
        return _err(str(e), 500)


@admin_bp.route("/backup-snapshot", methods=["POST"])
def trigger_snapshot():
    """Manually trigger a snapshot right now, instead of waiting for the interval."""
    if not _require_admin():
        return _err("Forbidden", 403)
    try:
        ok = backup_service.run_snapshot()
        if not ok:
            return _err("Snapshot failed or backups are not configured", 500)
        return _ok({"snapshot": "uploaded"})
    except Exception as e:
        logger.error(f"[Admin] backup-snapshot failed: {e}")
        return _err(str(e), 500)


@admin_bp.route("/restore-backup", methods=["POST"])
def restore_backup():
    """
    Disaster recovery: pulls the latest snapshot down over the live DB file.
    Destructive — requires explicit confirm:true in the body on top of the
    admin key, so this can never fire from a stray or scripted request.
    """
    if not _require_admin():
        return _err("Forbidden", 403)

    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return _err('Pass {"confirm": true} to proceed — this overwrites the live database')

    try:
        ok = backup_service.restore_latest()
        if not ok:
            return _err("Restore failed — see server logs", 500)
        return _ok({"restored": True})
    except Exception as e:
        logger.error(f"[Admin] restore-backup failed: {e}")
        return _err(str(e), 500)


@admin_bp.route("/health", methods=["GET"])
def combined_health():
    """One view: backup status + Unity connection status."""
    if not _require_admin():
        return _err("Forbidden", 403)
    import unity_bridge
    try:
        return _ok({
            "backup": backup_service.get_status(),
            "unity":  unity_bridge.get_status(),
        })
    except Exception as e:
        logger.error(f"[Admin] health failed: {e}")
        return _err(str(e), 500)


# ─── Moderation / ToS enforcement ───────────────────────────────────────────

@admin_bp.route("/moderation/active", methods=["GET"])
def moderation_active():
    """Every account currently timed out, soonest-expiring last."""
    if not _require_admin():
        return _err("Forbidden", 403)
    try:
        return _ok({"timeouts": moderation.list_active_timeouts()})
    except Exception as e:
        logger.error(f"[Admin] moderation/active failed: {e}")
        return _err(str(e), 500)


@admin_bp.route("/moderation/timeout", methods=["POST"])
def moderation_timeout():
    """
    Manually suspend a user's account for a ToS violation.
    Body: { "user_id": "...", "reason": "...", "duration_minutes": 60 }
    """
    if not _require_admin():
        return _err("Forbidden", 403)

    body     = request.get_json(silent=True) or {}
    user_id  = body.get("user_id")
    reason   = body.get("reason")
    duration = body.get("duration_minutes")

    if not user_id or not reason:
        return _err("user_id and reason are required")
    if not isinstance(duration, int) or duration <= 0:
        return _err("duration_minutes must be a positive integer")

    try:
        result = moderation.timeout_user(user_id, reason, duration, category="manual", created_by="admin")
        return _ok({"timeout": result})
    except Exception as e:
        logger.error(f"[Admin] moderation/timeout failed: {e}")
        return _err(str(e), 500)


@admin_bp.route("/moderation/clear", methods=["POST"])
def moderation_clear():
    """Lift an active timeout early. Body: { "user_id": "..." }"""
    if not _require_admin():
        return _err("Forbidden", 403)

    body    = request.get_json(silent=True) or {}
    user_id = body.get("user_id")
    if not user_id:
        return _err("user_id is required")

    try:
        cleared = moderation.clear_timeout(user_id)
        if not cleared:
            return _err("No active timeout for this user", 404)
        return _ok({"cleared": True, "user_id": user_id})
    except Exception as e:
        logger.error(f"[Admin] moderation/clear failed: {e}")
        return _err(str(e), 500)


@admin_bp.route("/audit-log", methods=["GET"])
def audit_log():
    """
    Recent Permission Bridge audit entries — every AI-node action, allowed
    or blocked, with the human-readable reason. Entries now carry user_id
    (threaded through from workflow_engine.py's RunContext), so pass
    ?user_id=... to scope to one tenant. Entries recorded before this field
    existed have no user_id and won't match a scoped query.
    Still operator-only behind X-Admin-Key for now — a self-service,
    per-user "why did my workflow do that" view is the actual end state
    (roadmap Section 9), but that's a separate frontend surface, not just
    this filter.
    Query params: limit (default 50, max 500), user_id (optional)
    """
    if not _require_admin():
        return _err("Forbidden", 403)

    try:
        limit = min(int(request.args.get("limit", 50)), 500)
    except (TypeError, ValueError):
        return _err("limit must be an integer")

    user_id = request.args.get("user_id") or None

    try:
        import node_library
        bridge, _ = node_library.get_bridge()
        entries = bridge.get_audit_log(limit, user_id=user_id)
        return _ok({"entries": entries, "count": len(entries)})
    except Exception as e:
        logger.error(f"[Admin] audit-log failed: {e}")
        return _err(str(e), 500)


def register_admin_routes(app):
    app.register_blueprint(admin_bp)
    logger.info("[Admin] Routes registered under /api/admin")
