"""
subscription_manager.py — Xoltra Subscription & Usage Tracking

Multi-tenant subscription tiers, limit enforcement, feature access,
and usage recording.

Tiers (4, per product spec):
    free_trial — limited tokens, most features unlocked to try everything
    basic      — more tokens than trial, limited feature/agent access
    premium    — more tokens, all features unlocked
    executive  — pay-as-you-go, unmetered, billed on actual usage

Bug fixed: llm.py calls sm.record_usage(user_id, tokens) at 3 call sites,
but this module only ever defined deduct_usage(). That mismatch was
silently swallowed by llm.py's try/except, so usage was NEVER recorded —
every tier's limits were unenforceable and executive billing always read
$0. record_usage() is now a thin, correctly-named wrapper around
deduct_usage(), so the calls llm.py already makes actually work.
"""

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from flask import Blueprint, request, jsonify

import knowledge_db as kdb
from auth import require_auth, get_current_user_id

logger = logging.getLogger(__name__)

subscription_bp = Blueprint("subscription", __name__, url_prefix="/api/usage")


# ═══════════════════════════════════════════════════
# PLAN DEFINITIONS — 4 tiers
# ═══════════════════════════════════════════════════

ALL_AGENTS = {
    "router", "clarifier", "architect", "critic", "operator",
    "validator", "compiler", "knowledge_retriever", "workflow_builder",
    "qa", "researcher", "document_processor",
}

ALL_TOOLS    = {"web_search", "code_executor", "database_query", "api_caller", "file_system"}
BASIC_TOOLS  = {"web_search"}

ALL_FEATURES = {"knowledge_engine", "workflow_builder", "simulation", "document_pipeline", "qa", "personalization"}

PLANS = {
    "free_trial": {
        "label":                    "Free Trial",
        "monthly_tokens":           5_000,
        "context_window":           8_000,
        "max_executions_per_month": 20,
        "max_workflows":            3,
        "max_knowledge_nodes":      50,
        "allowed_tiers":            {"simple", "medium", "complex"},
        "allowed_agents":           ALL_AGENTS,
        "allowed_tools":            ALL_TOOLS,
        "features":                 ALL_FEATURES,   # most access, to let people try everything
        "trial_days":               14,
        "pay_as_you_go":            False,
    },
    "basic": {
        "label":                    "Basic",
        "monthly_tokens":           50_000,
        "context_window":           8_000,
        "max_executions_per_month": 100,
        "max_workflows":            10,
        "max_knowledge_nodes":      200,
        "allowed_tiers":            {"simple", "medium"},
        "allowed_agents":           {"router", "clarifier", "architect", "critic", "validator", "compiler", "qa"},
        "allowed_tools":            BASIC_TOOLS,
        "features":                 {"qa", "document_pipeline", "personalization"},  # limited access
        "pay_as_you_go":            False,
    },
    "premium": {
        "label":                    "Premium",
        "monthly_tokens":           500_000,
        "context_window":           32_000,
        "max_executions_per_month": 2000,
        "max_workflows":            200,
        "max_knowledge_nodes":      5000,
        "allowed_tiers":            {"simple", "medium", "complex"},
        "allowed_agents":           ALL_AGENTS,
        "allowed_tools":            ALL_TOOLS,
        "features":                 ALL_FEATURES,   # everything unlocked
        "pay_as_you_go":            False,
    },
    "executive": {
        "label":                    "Executive",
        "monthly_tokens":           None,   # unmetered — billed per token instead
        "context_window":           32_000,
        "max_executions_per_month": None,
        "max_workflows":            None,
        "max_knowledge_nodes":      None,
        "allowed_tiers":            {"simple", "medium", "complex"},
        "allowed_agents":           ALL_AGENTS,
        "allowed_tools":            ALL_TOOLS,
        "features":                 ALL_FEATURES,
        "pay_as_you_go":            True,
        "cost_per_million_tokens":  2.50,   # USD — used to compute amount owed
    },
}

_subs_tables_created = False


def init_subs_tables():
    global _subs_tables_created
    if _subs_tables_created:
        return

    conn   = kdb._get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id            TEXT PRIMARY KEY,
            plan_id            TEXT NOT NULL,
            status             TEXT NOT NULL,
            activated_at       TEXT NOT NULL,
            expires_at         TEXT,
            payment_reference  TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_records (
            id            TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL,
            tokens_used   INTEGER NOT NULL,
            model_name    TEXT,
            agent_name    TEXT,
            execution_id  TEXT,
            timestamp     TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_user_time ON usage_records(user_id, timestamp)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_monthly (
            user_id           TEXT NOT NULL,
            month             TEXT NOT NULL,
            total_tokens      INTEGER DEFAULT 0,
            total_executions  INTEGER DEFAULT 0,
            total_api_calls   INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, month)
        )
    """)
    conn.commit()
    _subs_tables_created = True
    logger.info("[SubscriptionManager] Tables initialized")


def _get_current_month_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ═══════════════════════════════════════════════════
# ACTIVATION
# ═══════════════════════════════════════════════════

def activate_trial(user_id: str) -> bool:
    """Called from auth.register() for every new user."""
    init_subs_tables()

    now     = datetime.now(timezone.utc)
    expires = now + timedelta(days=PLANS["free_trial"]["trial_days"])

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO subscriptions (user_id, plan_id, status, activated_at, expires_at)
        VALUES (?, 'free_trial', 'active', ?, ?)
    """, (user_id, now.isoformat(), expires.isoformat()))
    conn.commit()

    logger.info(f"[SubscriptionManager] Trial activated for user: {user_id}")
    return True


def activate_plan(user_id: str, plan_id: str, payment_ref: Optional[str] = None) -> bool:
    """Activate/switch a user to a paid plan."""
    if plan_id not in PLANS:
        raise ValueError(f"Unknown plan_id: {plan_id}")

    init_subs_tables()
    now = datetime.now(timezone.utc)

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO subscriptions (user_id, plan_id, status, activated_at, expires_at, payment_reference)
        VALUES (?, ?, 'active', ?, NULL, ?)
    """, (user_id, plan_id, now.isoformat(), payment_ref))

    month_str = _get_current_month_str()
    cursor.execute("""
        INSERT OR IGNORE INTO usage_monthly (user_id, month, total_tokens, total_executions, total_api_calls)
        VALUES (?, ?, 0, 0, 0)
    """, (user_id, month_str))
    conn.commit()

    logger.info(f"[SubscriptionManager] Plan '{plan_id}' activated for user: {user_id}")
    return True


# ═══════════════════════════════════════════════════
# QUERIES
# ═══════════════════════════════════════════════════

def get_user_subscription(user_id: str) -> Optional[Dict[str, Any]]:
    init_subs_tables()
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT plan_id, status, activated_at, expires_at FROM subscriptions WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    if not row:
        return None
    return dict(row)


def get_usage_summary(user_id: str) -> Dict[str, Any]:
    """
    Powers GET /api/usage/summary — the Knowledge page's token/billing cards.
    For pay-as-you-go plans (executive), also returns estimated_cost.
    """
    init_subs_tables()
    month_str = _get_current_month_str()

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT total_tokens, total_executions FROM usage_monthly
        WHERE user_id = ? AND month = ?
    """, (user_id, month_str))
    row = cursor.fetchone()

    sub     = get_user_subscription(user_id)
    plan_id = sub["plan_id"] if sub else "free_trial"
    plan    = PLANS.get(plan_id, PLANS["free_trial"])

    used_tokens     = row["total_tokens"] if row else 0
    used_executions = row["total_executions"] if row else 0

    monthly_tokens   = plan["monthly_tokens"]
    remaining_tokens = None if monthly_tokens is None else max(0, monthly_tokens - used_tokens)

    max_executions        = plan["max_executions_per_month"]
    remaining_executions  = None if max_executions is None else max(0, max_executions - used_executions)

    summary = {
        "month":                 month_str,
        "plan_id":               plan_id,
        "plan_label":            plan["label"],
        "pay_as_you_go":         plan.get("pay_as_you_go", False),
        "tokens_used":           used_tokens,
        "tokens_limit":          monthly_tokens,
        "tokens_remaining":      remaining_tokens,
        "executions_used":       used_executions,
        "executions_limit":      max_executions,
        "executions_remaining":  remaining_executions,
    }

    if plan.get("pay_as_you_go"):
        rate = plan.get("cost_per_million_tokens", 0)
        summary["cost_per_million_tokens"] = rate
        summary["estimated_cost"] = round((used_tokens / 1_000_000) * rate, 2)

    if sub and sub.get("expires_at"):
        summary["trial_ends_at"] = sub["expires_at"]

    return summary


def get_remaining_tokens(user_id: str) -> Optional[int]:
    return get_usage_summary(user_id)["tokens_remaining"]


def get_context_window(user_id: str) -> int:
    sub     = get_user_subscription(user_id)
    plan_id = sub["plan_id"] if sub else "free_trial"
    return PLANS.get(plan_id, PLANS["free_trial"])["context_window"]


# ═══════════════════════════════════════════════════
# ACCESS CONTROL
# ═══════════════════════════════════════════════════

def check_permission(user_id: str, feature: str) -> bool:
    sub = get_user_subscription(user_id)
    if not sub or sub["status"] != "active":
        return False
    plan = PLANS.get(sub["plan_id"])
    return bool(plan) and feature in plan["features"]


def check_agent_access(user_id: str, agent_name: str) -> bool:
    sub = get_user_subscription(user_id)
    if not sub or sub["status"] != "active":
        return False
    plan = PLANS.get(sub["plan_id"])
    if not plan:
        return False
    return agent_name.lower() in [a.lower() for a in plan["allowed_agents"]]


def check_tool_access(user_id: str, tool_name: str) -> bool:
    sub = get_user_subscription(user_id)
    if not sub or sub["status"] != "active":
        return False
    plan = PLANS.get(sub["plan_id"])
    return bool(plan) and tool_name in plan["allowed_tools"]


def can_execute(user_id: str) -> tuple[bool, str]:
    sub = get_user_subscription(user_id)
    if not sub:
        return False, "No active subscription found"
    if sub["status"] != "active":
        return False, f"Subscription is {sub['status']}"

    if sub["expires_at"]:
        expiry = datetime.fromisoformat(sub["expires_at"])
        if datetime.now(timezone.utc) > expiry:
            return False, "Subscription has expired"

    plan_id = sub["plan_id"]
    plan    = PLANS.get(plan_id, PLANS["free_trial"])

    # Executive is pay-as-you-go — never blocked on token/execution ceilings
    if plan.get("pay_as_you_go"):
        return True, "Execution allowed (pay-as-you-go)"

    summary = get_usage_summary(user_id)
    if summary["tokens_remaining"] is not None and summary["tokens_remaining"] <= 0:
        return False, "Monthly token limit exceeded. Please upgrade your plan."
    if summary["executions_remaining"] is not None and summary["executions_remaining"] <= 0:
        return False, "Monthly execution limit exceeded. Please upgrade your plan."

    return True, "Execution allowed"


# ═══════════════════════════════════════════════════
# USAGE TRACKING
# ═══════════════════════════════════════════════════

def deduct_usage(user_id: str, tokens_used: int, model_name: Optional[str] = None,
                  agent_name: Optional[str] = None, execution_id: Optional[str] = None) -> bool:
    init_subs_tables()
    if tokens_used <= 0:
        return True

    now       = datetime.now(timezone.utc)
    month_str = _get_current_month_str()
    record_id = str(uuid.uuid4())

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO usage_records (id, user_id, tokens_used, model_name, agent_name, execution_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (record_id, user_id, tokens_used, model_name, agent_name, execution_id, now.isoformat()))

        cursor.execute("SELECT 1 FROM usage_monthly WHERE user_id = ? AND month = ?", (user_id, month_str))
        if cursor.fetchone():
            cursor.execute("""
                UPDATE usage_monthly
                SET total_tokens = total_tokens + ?, total_api_calls = total_api_calls + 1
                WHERE user_id = ? AND month = ?
            """, (tokens_used, user_id, month_str))
        else:
            cursor.execute("""
                INSERT INTO usage_monthly (user_id, month, total_tokens, total_executions, total_api_calls)
                VALUES (?, ?, ?, 0, 1)
            """, (user_id, month_str, tokens_used))

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"[SubscriptionManager] Failed to deduct usage for {user_id}: {e}")
        return False


def record_usage(user_id: str, tokens_used: int, model_name: Optional[str] = None) -> bool:
    """
    FIX: llm.py calls sm.record_usage(user_id, tokens) — this name never
    existed before (only deduct_usage did), so every usage write silently
    failed. This wrapper makes the name llm.py actually calls exist.
    """
    return deduct_usage(user_id, tokens_used, model_name=model_name)


def record_execution(user_id: str):
    init_subs_tables()
    month_str = _get_current_month_str()

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM usage_monthly WHERE user_id = ? AND month = ?", (user_id, month_str))
        if cursor.fetchone():
            cursor.execute("""
                UPDATE usage_monthly SET total_executions = total_executions + 1
                WHERE user_id = ? AND month = ?
            """, (user_id, month_str))
        else:
            cursor.execute("""
                INSERT INTO usage_monthly (user_id, month, total_tokens, total_executions, total_api_calls)
                VALUES (?, ?, 0, 1, 0)
            """, (user_id, month_str))
        conn.commit()
    except Exception as e:
        logger.error(f"[SubscriptionManager] Failed to record execution for {user_id}: {e}")


# ═══════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════

def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status

def _ok(data: dict):
    return jsonify({"success": True, **data})


@subscription_bp.route("/summary", methods=["GET"])
@require_auth
def route_summary():
    """Powers the Knowledge page's token usage / billing cards."""
    user_id = get_current_user_id()
    try:
        return _ok({"summary": get_usage_summary(user_id)})
    except Exception as e:
        return _err(f"Failed to load usage summary: {e}", 500)


@subscription_bp.route("/plans", methods=["GET"])
def route_plans():
    """Public — powers the pricing/upgrade UI. No preamble/internals leaked."""
    return _ok({
        "plans": [
            {
                "id":                plan_id,
                "label":             p["label"],
                "monthly_tokens":    p["monthly_tokens"],
                "pay_as_you_go":     p.get("pay_as_you_go", False),
                "cost_per_million":  p.get("cost_per_million_tokens"),
                "features":          sorted(p["features"]),
            }
            for plan_id, p in PLANS.items()
        ]
    })


@subscription_bp.route("/upgrade", methods=["POST"])
@require_auth
def route_upgrade():
    user_id = get_current_user_id()
    body    = request.get_json(silent=True) or {}
    plan_id = body.get("plan_id")

    if plan_id not in PLANS:
        return _err(f"Unknown plan_id: {plan_id}")

    try:
        activate_plan(user_id, plan_id, payment_ref=body.get("payment_reference"))
        return _ok({"plan_id": plan_id})
    except Exception as e:
        return _err(f"Upgrade failed: {e}", 500)
