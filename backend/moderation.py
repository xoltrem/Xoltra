"""
moderation.py — ToS enforcement: escalating timeouts for abusive behavior.

A "timeout" is a temporary account suspension: once active, every
@require_auth route returns 403 until it expires — separate from
rate_limit.py, which throttles request *rate* per IP but never blocks an
account outright.

Two ways a timeout gets created:
  1. Automatic — record_violation() escalates duration on repeat offenses
     by the same user in the same category within a lookback window.
  2. Manual — an admin calls POST /api/admin/moderation/timeout.
"""

import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import knowledge_db as kdb

logger = logging.getLogger(__name__)
_tables_created = False

# Nth violation in a category (within the lookback window) gets
# ESCALATION_MINUTES[N-1]; once past the list, it repeats the last value.
ESCALATION_MINUTES = [15, 60, 24 * 60, 7 * 24 * 60]  # 15m -> 1h -> 24h -> 7d
VIOLATION_WINDOW_HOURS = int(os.environ.get("MODERATION_VIOLATION_WINDOW_HOURS", 24 * 30))


def init_moderation_tables():
    global _tables_created
    if _tables_created:
        return
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS moderation_violations (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        category TEXT NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS moderation_timeouts (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        category TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        cleared_at TEXT
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mod_violations_user ON moderation_violations(user_id, category, created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mod_timeouts_user ON moderation_timeouts(user_id, expires_at)")
    conn.commit()
    _tables_created = True
    logger.info("[Moderation] Tables initialized")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def timeout_user(user_id: str, reason: str, duration_minutes: int,
                  category: str = "manual", created_by: str = "admin") -> dict:
    """Suspends a user's account for duration_minutes. Stacks are allowed — get_active_timeout() always returns the latest-expiring one."""
    init_moderation_tables()
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    now     = _now()
    expires = now + timedelta(minutes=duration_minutes)
    row_id  = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO moderation_timeouts (id, user_id, reason, category, created_by, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (row_id, user_id, reason, category, created_by, now.isoformat(), expires.isoformat()))
    conn.commit()
    logger.warning(f"[Moderation] user={user_id} timed out {duration_minutes}m by {created_by} — {reason}")
    return {"id": row_id, "user_id": user_id, "reason": reason, "category": category, "expires_at": expires.isoformat()}


def get_active_timeout(user_id: str) -> Optional[dict]:
    """The current active timeout for a user, or None if they're clear to proceed."""
    init_moderation_tables()
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, reason, category, expires_at FROM moderation_timeouts
        WHERE user_id = ? AND cleared_at IS NULL AND expires_at > ?
        ORDER BY expires_at DESC LIMIT 1
    """, (user_id, _now().isoformat()))
    row = cursor.fetchone()
    if not row:
        return None
    return {"id": row["id"], "reason": row["reason"], "category": row["category"], "expires_at": row["expires_at"]}


def clear_timeout(user_id: str) -> bool:
    """Admin override: lift a timeout early. Returns False if nothing active to clear."""
    init_moderation_tables()
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE moderation_timeouts SET cleared_at = ?
        WHERE user_id = ? AND cleared_at IS NULL AND expires_at > ?
    """, (_now().isoformat(), user_id, _now().isoformat()))
    conn.commit()
    return cursor.rowcount > 0


def record_violation(user_id: str, category: str, detail: str = "") -> Optional[dict]:
    """
    Logs one violation. If the count of same-category violations within the
    lookback window has now crossed the next rung of ESCALATION_MINUTES,
    automatically issues a timeout and returns it — otherwise returns None.
    Never raises: a moderation hiccup must never break the request it's
    attached to.
    """
    try:
        init_moderation_tables()
        conn   = kdb._get_conn()
        cursor = conn.cursor()
        now = _now()
        cursor.execute("""
            INSERT INTO moderation_violations (id, user_id, category, detail, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), user_id, category, detail, now.isoformat()))
        conn.commit()

        window_start = (now - timedelta(hours=VIOLATION_WINDOW_HOURS)).isoformat()
        cursor.execute("""
            SELECT COUNT(*) as c FROM moderation_violations
            WHERE user_id = ? AND category = ? AND created_at > ?
        """, (user_id, category, window_start))
        count = cursor.fetchone()["c"]

        duration = ESCALATION_MINUTES[min(count - 1, len(ESCALATION_MINUTES) - 1)]
        return timeout_user(
            user_id, reason=f"Automatic timeout — {count} '{category}' violation(s) in {VIOLATION_WINDOW_HOURS}h",
            duration_minutes=duration, category=category, created_by="system",
        )
    except Exception as e:
        logger.error(f"[Moderation] record_violation failed for user={user_id}: {e}")
        return None


def list_active_timeouts() -> list:
    """For the admin panel — every currently-active suspension, soonest-expiring last."""
    init_moderation_tables()
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, reason, category, created_by, created_at, expires_at
        FROM moderation_timeouts WHERE cleared_at IS NULL AND expires_at > ?
        ORDER BY expires_at DESC
    """, (_now().isoformat(),))
    return [dict(r) for r in cursor.fetchall()]
