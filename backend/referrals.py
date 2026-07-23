"""
referrals.py, Referral codes: generate, attribute a signup, report stats.

Every user gets a stable short code on first request. Attribution happens
once, at signup, from two call sites:
  - auth.py's /register (password signup), direct, same process.
  - auth.py's /oauth-issue (Google OAuth signup, called by the separate
    Node auth-service after OTP verification), the ref code has to
    travel through that whole flow first; see auth-service/auth.js for
    the Redis-backed relay that makes that possible.

A user can only ever be attributed once (referred_user_id is UNIQUE),
calling record_signup twice for the same user is a safe no-op, not a
double-count.
"""

import logging
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Optional

from flask import Blueprint, jsonify

import knowledge_db as kdb
from auth import require_auth, get_current_user_id

logger = logging.getLogger(__name__)

referrals_bp = Blueprint("referrals", __name__, url_prefix="/api/referrals")

_tables_created = False
_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LEN = 7


def init_referral_tables():
    global _tables_created
    if _tables_created:
        return
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referral_codes (
            user_id    TEXT PRIMARY KEY,
            code       TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referral_signups (
            id                TEXT PRIMARY KEY,
            referrer_user_id  TEXT NOT NULL,
            referred_user_id  TEXT UNIQUE NOT NULL,
            code_used         TEXT NOT NULL,
            signed_up_at      TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_referral_signups_referrer ON referral_signups(referrer_user_id)")
    conn.commit()
    _tables_created = True


def _generate_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))


def get_or_create_code(user_id: str) -> str:
    init_referral_tables()
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM referral_codes WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return row["code"]

    # Collision odds at 7 chars over [A-Z0-9] are astronomically low
    # (36^7), but check anyway rather than trust math under a UNIQUE
    # constraint that would otherwise just throw.
    for _ in range(5):
        code = _generate_code()
        cursor.execute("SELECT 1 FROM referral_codes WHERE code = ?", (code,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO referral_codes (user_id, code, created_at) VALUES (?, ?, ?)",
                (user_id, code, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()
            return code
    raise RuntimeError("Could not generate a unique referral code after 5 attempts")


def record_signup(code: Optional[str], referred_user_id: str) -> bool:
    """
    Called once, right after a new user is created. Safe to call with
    code=None (most signups have no referral) or an unknown/self code,
    returns False rather than raising, since a bad referral code should
    never block someone from finishing signup.
    """
    if not code:
        return False
    init_referral_tables()
    conn = kdb._get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM referral_codes WHERE code = ?", (code.strip().upper(),))
    row = cursor.fetchone()
    if not row:
        return False
    referrer_user_id = row["user_id"]

    if referrer_user_id == referred_user_id:
        logger.warning(f"[Referrals] ignored self-referral attempt by {referred_user_id[:8]}")
        return False

    try:
        cursor.execute(
            "INSERT INTO referral_signups (id, referrer_user_id, referred_user_id, code_used, signed_up_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), referrer_user_id, referred_user_id, code, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        return True
    except Exception as e:
        # referred_user_id UNIQUE constraint hit = already attributed,
        # not an error worth logging loudly.
        if "UNIQUE" not in str(e):
            logger.error(f"[Referrals] record_signup failed: {e}")
        return False


def get_referral_stats(user_id: str) -> dict:
    init_referral_tables()
    code = get_or_create_code(user_id)
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as n FROM referral_signups WHERE referrer_user_id = ?", (user_id,))
    count = cursor.fetchone()["n"]
    return {"code": code, "signup_count": count}


def _ok(data: dict):
    return jsonify({"success": True, **data})


@referrals_bp.route("/me", methods=["GET"])
@require_auth
def route_me():
    user_id = get_current_user_id()
    return _ok(get_referral_stats(user_id))


def register_referral_routes(app):
    app.register_blueprint(referrals_bp)
    logger.info("[Referrals] Routes registered under /api/referrals")
