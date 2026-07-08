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

import knowledge_db as kdb
import subscription_manager as sm

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# JWT Configuration
# In production, this should be an environment variable
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-key-do-not-use-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

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
        is_active BOOLEAN NOT NULL DEFAULT 1
    )
    """)
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
            
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'error': 'Invalid token'}), 401
            
        return f(*args, **kwargs)
    return decorated

def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status

def _ok(data: dict):
    return jsonify({"success": True, **data})

# ═══════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════

@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new user."""
    init_auth_tables()
    
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password", "")
    
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
        sm.activate_trial(user_id)
        
        token = generate_token(user_id)
        
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
    
    logger.info(f"[Auth] User logged in: {email}")
    return _ok({
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"]
        }
    })

@auth_bp.route("/oauth-issue", methods=["POST"])
def oauth_issue():
    """
    Server-to-server only — called by auth-service/auth.js right after it
    verifies a Google OAuth + OTP login. Google confirms WHO the person is;
    this endpoint is what makes them an actual Xoltra user by finding or
    creating their account and handing back a normal Flask JWT — the same
    kind every other route (@require_auth) already understands.

    Not meant to be called directly by a browser. In production, restrict
    this route to the auth-service's IP or a shared internal secret header.
    """
    init_auth_tables()

    body  = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    source = body.get("source", "unknown")

    if not email:
        return _err("email is required")

    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if user:
        user_id = user["id"]
    else:
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        placeholder_hash = _hash_password(secrets.token_hex(32))  # OAuth users never use this
        cursor.execute("""
            INSERT INTO users (id, email, password_hash, created_at, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (user_id, email, placeholder_hash, now))
        conn.commit()
        sm.activate_trial(user_id)
        logger.info(f"[Auth] New user via {source}: {email} ({user_id})")

    token = generate_token(user_id)
    return _ok({
        "token": token,
        "user": {"id": user_id, "email": email},
    })


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

        sm.activate_trial(user_id)
        logger.info(f"[Auth] OAuth-created new user: {email} ({user_id})")

    token = generate_token(user_id)
    return _ok({"token": token, "user": {"id": user_id, "email": email}})
