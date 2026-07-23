"""
onedrive_routes.py — Premium feature: let a user back up their own
knowledge/workflow data to their own OneDrive.

Flow:
  1. GET  /api/premium/onedrive/connect   -> Microsoft consent URL
  2. GET  /api/premium/onedrive/callback  -> exchanges code for tokens, stores them
  3. POST /api/premium/onedrive/backup    -> exports the user's data, uploads
                                              to OneDrive, returns a summary

Uses the standard OAuth2 authorization-code flow against Microsoft identity
platform (login.microsoftonline.com) + Graph API (graph.microsoft.com).
Requires MS_CLIENT_ID / MS_CLIENT_SECRET / MS_REDIRECT_URI in env — degrades
to a clear "not configured" error otherwise, never crashes the app.
"""

import os
import json
import logging
from datetime import datetime, timezone

import requests
from flask import Blueprint, request, jsonify, redirect

import knowledge_db as kdb
import workflow_store
from auth import require_auth, get_current_user_id
import subscription_manager as sm
import crypto_utils

logger = logging.getLogger(__name__)

onedrive_bp = Blueprint("onedrive", __name__, url_prefix="/api/premium/onedrive")

MS_CLIENT_ID     = os.environ.get("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET")
MS_REDIRECT_URI  = os.environ.get("MS_REDIRECT_URI", "http://localhost:5001/api/premium/onedrive/callback")
MS_SCOPES        = "Files.ReadWrite.AppFolder offline_access User.Read"
AUTHORIZE_URL    = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL        = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_UPLOAD_URL = "https://graph.microsoft.com/v1.0/me/drive/special/approot:/{filename}:/content"

_tables_created = False


def init_onedrive_tables():
    global _tables_created
    if _tables_created:
        return
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS onedrive_tokens (
            user_id       TEXT PRIMARY KEY,
            access_token  TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at    TEXT NOT NULL,
            connected_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    _tables_created = True


def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


def _ok(data: dict):
    return jsonify({"success": True, **data})


def _require_premium(user_id: str):
    return sm.check_permission(user_id, "cloud_backup")


def _configured() -> bool:
    return bool(MS_CLIENT_ID and MS_CLIENT_SECRET)


@onedrive_bp.route("/connect", methods=["GET"])
@require_auth
def connect():
    """Returns the Microsoft consent URL the frontend should open."""
    user_id = get_current_user_id()
    if not _require_premium(user_id):
        return _err("OneDrive backup is a Premium/Executive feature", 403)
    if not _configured():
        return _err("OneDrive integration not configured on this server", 503)

    params = (
        f"client_id={MS_CLIENT_ID}&response_type=code"
        f"&redirect_uri={MS_REDIRECT_URI}&response_mode=query"
        f"&scope={MS_SCOPES.replace(' ', '%20')}&state={user_id}"
    )
    return _ok({"auth_url": f"{AUTHORIZE_URL}?{params}"})


@onedrive_bp.route("/callback", methods=["GET"])
def callback():
    """Microsoft redirects here with ?code&state=user_id. No @require_auth —
    the browser lands here directly from Microsoft's own redirect."""
    init_onedrive_tables()
    code = request.args.get("code")
    user_id = request.args.get("state")
    if not code or not user_id:
        return _err("Missing code or state")
    if not _configured():
        return _err("OneDrive integration not configured on this server", 503)

    try:
        resp = requests.post(TOKEN_URL, data={
            "client_id": MS_CLIENT_ID, "client_secret": MS_CLIENT_SECRET,
            "code": code, "redirect_uri": MS_REDIRECT_URI,
            "grant_type": "authorization_code", "scope": MS_SCOPES,
        }, timeout=10)
        resp.raise_for_status()
        tok = resp.json()

        conn = kdb._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO onedrive_tokens (user_id, access_token, refresh_token, expires_at, connected_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                access_token=excluded.access_token, refresh_token=excluded.refresh_token,
                expires_at=excluded.expires_at
        """, (user_id, crypto_utils.encrypt_secret(tok["access_token"]),
              crypto_utils.encrypt_secret(tok.get("refresh_token", "")),
              str(datetime.now(timezone.utc).timestamp() + tok.get("expires_in", 3600)),
              datetime.now(timezone.utc).isoformat()))
        conn.commit()

        frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
        return redirect(f"{frontend_url}/settings?onedrive=connected")
    except Exception as e:
        logger.error(f"[OneDrive] token exchange failed: {e}")
        return _err("Failed to connect OneDrive", 500)


def _get_valid_token(user_id: str):
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT access_token, refresh_token, expires_at FROM onedrive_tokens WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return None

    access_token = crypto_utils.decrypt_secret(row["access_token"])
    refresh_token = crypto_utils.decrypt_secret(row["refresh_token"])

    if float(row["expires_at"]) > datetime.now(timezone.utc).timestamp() + 60:
        return access_token

    # Refresh
    resp = requests.post(TOKEN_URL, data={
        "client_id": MS_CLIENT_ID, "client_secret": MS_CLIENT_SECRET,
        "refresh_token": refresh_token, "grant_type": "refresh_token", "scope": MS_SCOPES,
    }, timeout=10)
    resp.raise_for_status()
    tok = resp.json()
    cursor.execute(
        "UPDATE onedrive_tokens SET access_token=?, expires_at=? WHERE user_id=?",
        (crypto_utils.encrypt_secret(tok["access_token"]),
         str(datetime.now(timezone.utc).timestamp() + tok.get("expires_in", 3600)), user_id)
    )
    conn.commit()
    return tok["access_token"]


def _export_user_data(user_id: str) -> dict:
    goals     = kdb.get_nodes_by_type(user_id, "goal")
    workflows = workflow_store.list_workflows(user_id)
    insights  = kdb.get_nodes_by_type(user_id, "insight")
    documents = kdb.get_nodes_by_type(user_id, "document")
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "goals": goals, "workflows": workflows, "insights": insights, "documents": documents,
    }


@onedrive_bp.route("/backup", methods=["POST"])
@require_auth
def backup():
    """Exports the user's knowledge + workflows and uploads to their
    OneDrive app folder. Returns a summary of what was saved."""
    init_onedrive_tables()
    user_id = get_current_user_id()
    if not _require_premium(user_id):
        return _err("OneDrive backup is a Premium/Executive feature", 403)

    token = _get_valid_token(user_id)
    if not token:
        return _err("OneDrive not connected — call /connect first", 400)

    export = _export_user_data(user_id)
    body_bytes = json.dumps(export, default=str, indent=2).encode("utf-8")
    filename = f"xoltra-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"

    try:
        resp = requests.put(
            GRAPH_UPLOAD_URL.format(filename=filename),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            data=body_bytes, timeout=20,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"[OneDrive] upload failed for {user_id}: {e}")
        return _err(f"OneDrive upload failed: {e}", 502)

    summary = {
        "filename": filename,
        "size_bytes": len(body_bytes),
        "goals_saved": len(export["goals"]),
        "workflows_saved": len(export["workflows"]),
        "insights_saved": len(export["insights"]),
        "documents_saved": len(export["documents"]),
        "saved_at": export["exported_at"],
    }
    logger.info(f"[OneDrive] Backup saved for {user_id}: {filename} ({len(body_bytes)} bytes)")
    return _ok({"summary": summary})


@onedrive_bp.route("/status", methods=["GET"])
@require_auth
def status():
    init_onedrive_tables()
    user_id = get_current_user_id()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT connected_at FROM onedrive_tokens WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return _ok({
        "premium": _require_premium(user_id),
        "configured": _configured(),
        "connected": bool(row),
        "connected_at": row["connected_at"] if row else None,
    })


def register_onedrive_routes(app):
    app.register_blueprint(onedrive_bp)
    logger.info("[OneDrive] Routes registered under /api/premium/onedrive")
