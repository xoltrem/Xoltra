"""
auth.py — Xoltra Authentication Module

Handles user registration, login, JWT token generation/validation,
and provides the @require_auth decorator for API route protection.
"""

import os
import uuid
import hashlib
import secrets
import json
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Blueprint, request, jsonify, g

from rate_limit import rate_limit

import knowledge_db as kdb
# NOTE: subscription_manager is imported lazily inside functions below, not
# here at module level — it does `from auth import require_auth` at its own
# module level, so importing it here would create a circular import that
# crashes the app on boot the moment both modules are loaded.

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# JWT Configuration
# In production, this should be an environment variable
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-key-do-not-use-in-prod")

def _is_production() -> bool:
    return os.environ.get("XOLTRA_ENV", os.environ.get("FLASK_ENV", "development")).lower() == "production"

if _is_production() and JWT_SECRET == "dev-secret-key-do-not-use-in-prod":
    raise RuntimeError("JWT_SECRET must be set in production — refusing to start with the dev default.")

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# One acceptance decision covers both the Terms of Service AND the Privacy
# Notice (both dated with this effective date; the ToS incorporates the
# Privacy Notice by reference). Bump this string whenever either document's
# "Effective date" changes — every user is required to re-accept before
# using the account again, exactly like accepting the current version once.
CURRENT_POLICY_VERSION = "2026-07-13"

_auth_tables_created = False

def init_auth_tables():
    """Create users table in the shared SQLite database."""
    global _auth_tables_created
    if _auth_tables_created:
        return

    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        tos_status TEXT NOT NULL DEFAULT 'pending',
        tos_decided_at TEXT,
        tos_accepted_at TEXT,
        tos_version TEXT
    )
    """)
    # Existing installations may already have the users table.  Keep this
    # migration additive so every pre-existing account is asked once too.
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}
    if "tos_status" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tos_status TEXT NOT NULL DEFAULT 'pending'")
    if "tos_decided_at" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tos_decided_at TEXT")
    if "tos_accepted_at" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tos_accepted_at TEXT")
    if "tos_version" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tos_version TEXT")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS login_events (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        ip TEXT,
        user_agent TEXT,
        event TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_login_events_user ON login_events(user_id, created_at)")
    conn.commit()
    _auth_tables_created = True
    logger.info("[Auth] Tables initialized")

def _hash_password(password: str, salt: str = None) -> str:
    """Hash a password with an optional provided salt (or generate a new one)."""
    if salt is None:
        salt = secrets.token_hex(16)
    
    # Simple PBKDF2
    hash_obj = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        salt.encode('utf-8'), 
        100000
    )
    return f"{salt}${hash_obj.hex()}"

def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt, _ = password_hash.split('$', 1)
        return _hash_password(password, salt) == password_hash
    except ValueError:
        return False

def generate_token(user_id: str) -> str:
    """Generate a JWT token for the user."""
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.now(timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user_id() -> str:
    """Helper to get the current authenticated user ID from Flask global context."""
    return getattr(g, 'user_id', None)

def require_auth(f):
    """Decorator to require authentication on an API route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'Missing authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = payload.get('user_id')
            if not user_id:
                raise jwt.InvalidTokenError()

            # Store in flask.g for easy access in route handlers
            g.user_id = user_id

            # A declined or undecided Terms decision may only use the Terms
            # endpoint.  This makes the restriction real even if a client is
            # modified to reveal otherwise-hidden UI controls.
            if request.path != "/api/auth/terms":
                init_auth_tables()
                conn = kdb._get_conn()
                user = conn.execute(
                    "SELECT tos_status, tos_version FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if not user:
                    return jsonify({'success': False, 'error': 'User not found'}), 404
                if user["tos_status"] != "accepted" or user["tos_version"] != CURRENT_POLICY_VERSION:
                    return jsonify({
                        'success': False,
                        'error': 'Accept the Terms of Service and Privacy Notice to use account features',
                        'code': 'TERMS_NOT_ACCEPTED',
                        'tos_status': 'pending' if user["tos_version"] != CURRENT_POLICY_VERSION else user["tos_status"],
                        'policy_version': CURRENT_POLICY_VERSION,
                    }), 403

        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'error': 'Invalid token'}), 401

        # ToS enforcement: a valid token doesn't help if the account is
        # currently timed out. Checked on every authenticated request.
        try:
            import moderation
            active_timeout = moderation.get_active_timeout(user_id)
        except Exception as e:
            logger.error(f"[Auth] moderation check failed, failing open: {e}")
            active_timeout = None

        if active_timeout:
            return jsonify({
                'success':      False,
                'error':        f"Account temporarily suspended: {active_timeout['reason']}",
                'timeout':      True,
                'timeout_until': active_timeout['expires_at'],
                'category':     active_timeout['category'],
            }), 403

        return f(*args, **kwargs)
    return decorated

def _log_event(user_id: str, event: str):
    try:
        conn = kdb._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO login_events (id, user_id, ip, user_agent, event, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id,
             request.headers.get("X-Forwarded-For", request.remote_addr or ""),
             (request.headers.get("User-Agent") or "")[:200],
             event, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
    except Exception as e:
        logger.debug(f"[Auth] _log_event failed (non-fatal): {e}")

def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status

def _ok(data: dict):
    return jsonify({"success": True, **data})

# ═══════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════

@auth_bp.route("/register", methods=["POST"])
@rate_limit(limit=10, window_seconds=60)
def register():
    """Register a new user."""
    init_auth_tables()
    
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password", "")
    ref_code = (body.get("ref") or "").strip() or None
    
    if not email or not password:
        return _err("Email and password are required")
        
    if len(password) < 8:
        return _err("Password must be at least 8 characters")
        
    conn = kdb._get_conn()
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        return _err("Email already registered")
        
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    try:
        cursor.execute("""
            INSERT INTO users (id, email, password_hash, created_at, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (user_id, email, _hash_password(password), now))
        conn.commit()
        
        # Provision free trial subscription
        import subscription_manager as sm
        sm.activate_trial(user_id)

        if ref_code:
            import referrals
            referrals.record_signup(ref_code, user_id)
        
        token = generate_token(user_id)
        _log_event(user_id, "register")

        logger.info(f"[Auth] Registered new user: {email} ({user_id})")
        return _ok({
            "token": token,
            "user": {
                "id": user_id,
                "email": email
            }
        })
    except Exception as e:
        logger.error(f"[Auth] Registration failed: {e}")
        return _err("Registration failed", 500)

@auth_bp.route("/login", methods=["POST"])
@rate_limit(limit=10, window_seconds=60)
def login():
    """Authenticate and return a JWT token."""
    init_auth_tables()
    
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password", "")
    
    if not email or not password:
        return _err("Email and password are required")
        
    conn = kdb._get_conn()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, email, password_hash, is_active FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    
    if not user or not _verify_password(password, user["password_hash"]):
        return _err("Invalid email or password", 401)
        
    if not user["is_active"]:
        return _err("Account is disabled", 403)
        
    token = generate_token(user["id"])
    _log_event(user["id"], "login")

    logger.info(f"[Auth] User logged in: {email}")
    return _ok({
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"]
        }
    })

@auth_bp.route("/sessions", methods=["GET"])
@require_auth
def sessions():
    """Recent login/register events for the settings page activity log."""
    user_id = get_current_user_id()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ip, user_agent, event, created_at FROM login_events WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
        (user_id,)
    )
    rows = [dict(r) for r in cursor.fetchall()]
    return _ok({"sessions": rows})


@auth_bp.route("/terms", methods=["GET", "PUT"])
@require_auth
def terms():
    """
    Read or record the Terms of Service + Privacy Notice decision for this
    user. One decision covers both documents. Re-asked whenever
    CURRENT_POLICY_VERSION changes, even for users who accepted a prior
    version — their original acceptance record is kept, not overwritten,
    until they decide again.
    """
    user_id = get_current_user_id()
    conn = kdb._get_conn()
    cursor = conn.cursor()

    if request.method == "GET":
        row = cursor.execute(
            "SELECT tos_status, tos_decided_at, tos_accepted_at, tos_version FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            return _err("User not found", 404)
        data = dict(row)
        # Surface "pending" if they're on an outdated version, without
        # touching the stored record of what they actually agreed to.
        if data["tos_version"] != CURRENT_POLICY_VERSION:
            data["tos_status"] = "pending"
        data["current_policy_version"] = CURRENT_POLICY_VERSION
        return _ok({"terms": data})

    decision = (request.get_json(silent=True) or {}).get("decision")
    if decision not in ("accepted", "rejected"):
        return _err("decision must be 'accepted' or 'rejected'")

    row = cursor.execute("SELECT tos_status, tos_version FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return _err("User not found", 404)
    # Acceptance is a durable legal record, not a preference that can be
    # silently revoked by a later browser request — unless a new policy
    # version now requires a fresh decision.
    already_current = row["tos_status"] == "accepted" and row["tos_version"] == CURRENT_POLICY_VERSION
    if already_current and decision != "accepted":
        return _err("Accepted Terms cannot be changed", 409)

    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "UPDATE users SET tos_status = ?, tos_decided_at = ?, tos_accepted_at = ?, tos_version = ? WHERE id = ?",
        (decision, now, now if decision == "accepted" else None, CURRENT_POLICY_VERSION, user_id),
    )
    conn.commit()
    _log_event(user_id, f"terms_{decision}_v{CURRENT_POLICY_VERSION}")
    return _ok({"terms": {"tos_status": decision, "tos_decided_at": now,
                           "tos_accepted_at": now if decision == "accepted" else None,
                           "tos_version": CURRENT_POLICY_VERSION}})

@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():
    """Get current user profile."""
    user_id = get_current_user_id()
    
    conn = kdb._get_conn()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, email, created_at FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        return _err("User not found", 404)
        
    return _ok({
        "user": {
            "id": user["id"],
            "email": user["email"],
            "created_at": user["created_at"]
        }
    })

# ═══════════════════════════════════════════════════
# OAUTH HANDOFF — called only by auth-service, never by browsers directly
# ═══════════════════════════════════════════════════

INTERNAL_SERVICE_KEY = os.environ.get("INTERNAL_SERVICE_KEY", "dev-internal-key-do-not-use-in-prod")

if _is_production() and INTERNAL_SERVICE_KEY == "dev-internal-key-do-not-use-in-prod":
    raise RuntimeError("INTERNAL_SERVICE_KEY must be set in production — refusing to start with the dev default.")

@auth_bp.route("/oauth-issue", methods=["POST"])
def oauth_issue():
    """
    Called by auth-service (auth.js) AFTER it has already verified the
    person's identity via Google OAuth + email OTP. Gets or creates the
    matching Flask user and returns a normal Flask JWT, so a Google login
    and an email/password login both hand back the exact same kind of
    token every @require_auth route already expects.

    Protected by a shared internal-service key, NOT user-facing — this
    endpoint trusts that the caller already did real verification, so it
    must never be reachable directly from a browser.
    """
    init_auth_tables()

    if request.headers.get("X-Internal-Key") != INTERNAL_SERVICE_KEY:
        return _err("Forbidden", 403)

    body  = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    ref_code = (body.get("ref") or "").strip() or None
    if not email:
        return _err("email is required")

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, is_active FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if user:
        if not user["is_active"]:
            return _err("Account is disabled", 403)
        user_id = user["id"]
    else:
        # OAuth-verified accounts have no password of their own — store a
        # random value nobody can ever know or derive, rather than altering
        # the existing NOT NULL schema (keeps this change additive-only).
        user_id = str(uuid.uuid4())
        now     = datetime.now(timezone.utc).isoformat()
        unusable_password_hash = _hash_password(secrets.token_hex(32))

        cursor.execute("""
            INSERT INTO users (id, email, password_hash, created_at, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (user_id, email, unusable_password_hash, now))
        conn.commit()

        import subscription_manager as sm
        sm.activate_trial(user_id)

        if ref_code:
            import referrals
            referrals.record_signup(ref_code, user_id)

        logger.info(f"[Auth] OAuth-created new user: {email} ({user_id})")

    token = generate_token(user_id)
    _log_event(user_id, "google_oauth")
    return _ok({"token": token, "user": {"id": user_id, "email": email}})
