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


def register_admin_routes(app):
    app.register_blueprint(admin_bp)
    logger.info("[Admin] Routes registered under /api/admin")
