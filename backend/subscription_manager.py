"""
subscription_manager.py — Xoltra Subscription & Usage Tracking

Tiers (per the July 2026 pricing matrix — weekly token pools, strict
use-it-or-lose-it, no rollover, reset every Sunday 00:00 UTC):
    free_trial — 14-day trial, most features unlocked to try everything
    basic      — $17/mo "decoy" tier, 4 core agents, no overage
    premium    — $22/mo "sweet spot", all agents, overage available
    max        — $41/mo "power user", all agents, overage available

Overage ("Enterprise Pay-As-You-Go Layer"): once a premium/max user
exhausts their weekly pool, extra tokens are tracked (not blocked) at a
tiered rate — 0-100k extra tokens double rate, 100k+ triple rate. This is
COST TRACKING ONLY right now — no live billing is wired up (see
route_upgrade below), so overage_cost_cents accrues but nothing actually
charges a card yet.

Payment status: Stripe isn't connected yet (intentional — the pricing UI
isn't live, this is prep work). activate_plan() therefore always sets
payment_verified=False and every upgrade is rate-limited + audit-logged as
unverified, so there's a clean trail to reconcile once real Stripe
Checkout verification (see stripe_main.py) is wired up as the actual gate.

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
from auth import require_auth, get_current_user_id, _log_event, INTERNAL_SERVICE_KEY
from rate_limit import rate_limit_user

logger = logging.getLogger(__name__)

subscription_bp = Blueprint("subscription", __name__, url_prefix="/api/usage")


# ═══════════════════════════════════════════════════
# PLAN DEFINITIONS — pricing matrix, July 2026
# ═══════════════════════════════════════════════════

ALL_AGENTS = {
    "router", "clarifier", "architect", "critic", "operator",
    "validator", "compiler", "knowledge_retriever", "workflow_builder",
    "qa", "researcher", "document_processor",
}
# "4 Core Agents" per the pricing doc — the minimum usable pipeline
# (route -> clarify -> build -> check). Everything else needs an upgrade.
CORE_AGENTS = {"router", "clarifier", "architect", "qa"}

ALL_TOOLS    = {"web_search", "code_executor", "database_query", "api_caller", "file_system"}
BASIC_TOOLS  = {"web_search"}

ALL_FEATURES = {"knowledge_engine", "workflow_builder", "simulation", "document_pipeline", "qa", "personalization"}
PREMIUM_FEATURES = ALL_FEATURES | {"cloud_backup"}  # OneDrive export — premium/max only

# Enterprise pay-as-you-go overage rates (USD per 1,000 tokens), applied
# once a premium/max user exceeds their weekly pool. Tracked, not yet
# billed — see module docstring.
OVERAGE_TIER1_RATE_PER_1K = 0.002   # first 100,000 overage tokens/week
OVERAGE_TIER2_RATE_PER_1K = 0.003   # every overage token past that
OVERAGE_TIER1_CEILING     = 100_000

PLANS = {
    "free_trial": {
        "label":                   "Free Trial",
        "price_cents":             0,
        "weekly_tokens":           5_000,   # ~10,000 total across the 14-day trial (2 weekly resets)
        "context_window":          8_000,
        "max_executions_per_week": 20,
        "max_workflows":           3,
        "max_knowledge_nodes":     50,
        "allowed_tiers":           {"simple", "medium", "complex"},
        "allowed_agents":          ALL_AGENTS,
        "allowed_tools":           ALL_TOOLS,
        "features":                ALL_FEATURES,   # most access, to let people try everything
        "trial_days":              14,
        "overage_allowed":         False,
    },
    "basic": {
        "label":                   "Basic",
        "price_cents":             1_700,   # $17/mo
        "weekly_tokens":           56_000,
        "context_window":          8_000,
        "max_executions_per_week": 100,
        "max_workflows":           10,
        "max_knowledge_nodes":     200,
        "allowed_tiers":           {"simple", "medium"},
        "allowed_agents":          CORE_AGENTS,
        "allowed_tools":           BASIC_TOOLS,
        "features":                {"qa", "document_pipeline", "personalization"},
        "overage_allowed":         False,   # "decoy" tier — must upgrade, no pay-as-you-go safety net
    },
    "premium": {
        "label":                   "Premium",
        "price_cents":             2_200,   # $22/mo
        "weekly_tokens":           448_000,
        "context_window":          32_000,
        "max_executions_per_week": 2_000,
        "max_workflows":           200,
        "max_knowledge_nodes":     5_000,
        "allowed_tiers":           {"simple", "medium", "complex"},
        "allowed_agents":          ALL_AGENTS,
        "allowed_tools":           ALL_TOOLS,
        "features":                PREMIUM_FEATURES,
        "overage_allowed":         True,
    },
    "max": {
        "label":                   "Max",
        "price_cents":             4_100,   # $41/mo
        "weekly_tokens":           1_190_000,
        "context_window":          32_000,
        "max_executions_per_week": None,   # unrestricted execution count at this tier
        "max_workflows":           None,
        "max_knowledge_nodes":     None,
        "allowed_tiers":           {"simple", "medium", "complex"},
        "allowed_agents":          ALL_AGENTS,
        "allowed_tools":           ALL_TOOLS,
        "features":                PREMIUM_FEATURES,
        "overage_allowed":         True,
    },
}

# "executive" was the old always-metered plan id. Keep a read-only alias so
# any existing subscriptions/tests referencing it don't 404 — new
# activations should use "max" (which now carries the overage layer).
PLANS["executive"] = PLANS["max"]

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
            payment_reference  TEXT,
            payment_verified   INTEGER NOT NULL DEFAULT 0
        )
    """)
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(subscriptions)").fetchall()}
    if "payment_verified" not in columns:
        cursor.execute("ALTER TABLE subscriptions ADD COLUMN payment_verified INTEGER NOT NULL DEFAULT 0")

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
        CREATE TABLE IF NOT EXISTS usage_weekly (
            user_id            TEXT NOT NULL,
            week_start         TEXT NOT NULL,
            total_tokens       INTEGER DEFAULT 0,
            total_executions   INTEGER DEFAULT 0,
            total_api_calls    INTEGER DEFAULT 0,
            overage_tokens     INTEGER DEFAULT 0,
            overage_cost_cents INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, week_start)
        )
    """)
    conn.commit()
    _subs_tables_created = True
    logger.info("[SubscriptionManager] Tables initialized")


def _get_current_week_start() -> str:
    """
    ISO date (YYYY-MM-DD) of the most recent Sunday 00:00 UTC — the reset
    boundary. Tokens never roll over, so this is the whole partition key.
    """
    now = datetime.now(timezone.utc)
    # Python's weekday(): Monday=0 ... Sunday=6. Days since the last Sunday:
    days_since_sunday = (now.weekday() + 1) % 7
    week_start = (now - timedelta(days=days_since_sunday)).date()
    return week_start.isoformat()


def _overage_cost_cents(overage_tokens: int) -> int:
    """Tiered rate: first 100k overage tokens at tier 1, the rest at tier 2. Returns whole cents."""
    if overage_tokens <= 0:
        return 0
    tier1_tokens = min(overage_tokens, OVERAGE_TIER1_CEILING)
    tier2_tokens = max(0, overage_tokens - OVERAGE_TIER1_CEILING)
    cost_usd = (tier1_tokens / 1000) * OVERAGE_TIER1_RATE_PER_1K + (tier2_tokens / 1000) * OVERAGE_TIER2_RATE_PER_1K
    return round(cost_usd * 100)


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


def activate_plan(user_id: str, plan_id: str, payment_ref: Optional[str] = None,
                   payment_verified: bool = False) -> bool:
    """
    Activate/switch a user to a paid plan.

    payment_verified defaults to False and MUST be passed True explicitly by
    a caller that actually checked payment_ref against Stripe (or another
    real payment provider) — see stripe_main.py. Nothing in this module
    verifies payment_ref itself; it's just stored for the audit trail.
    """
    if plan_id not in PLANS:
        raise ValueError(f"Unknown plan_id: {plan_id}")

    init_subs_tables()
    now = datetime.now(timezone.utc)

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO subscriptions (user_id, plan_id, status, activated_at, expires_at, payment_reference, payment_verified)
        VALUES (?, ?, 'active', ?, NULL, ?, ?)
    """, (user_id, plan_id, now.isoformat(), payment_ref, int(payment_verified)))

    week_start = _get_current_week_start()
    cursor.execute("""
        INSERT OR IGNORE INTO usage_weekly (user_id, week_start, total_tokens, total_executions, total_api_calls, overage_tokens, overage_cost_cents)
        VALUES (?, ?, 0, 0, 0, 0, 0)
    """, (user_id, week_start))
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
        "SELECT plan_id, status, activated_at, expires_at, payment_verified FROM subscriptions WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    if not row:
        return None
    return dict(row)


def get_usage_summary(user_id: str) -> Dict[str, Any]:
    """
    Powers GET /api/usage/summary — the Knowledge page's token/billing cards.
    Weekly pools reset every Sunday 00:00 UTC, no rollover. For overage-
    eligible plans (premium/max) that have exceeded their pool, also
    returns overage_tokens and overage_cost_cents (tracked, not yet billed).
    """
    init_subs_tables()
    week_start = _get_current_week_start()

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT total_tokens, total_executions, overage_tokens, overage_cost_cents FROM usage_weekly
        WHERE user_id = ? AND week_start = ?
    """, (user_id, week_start))
    row = cursor.fetchone()

    sub     = get_user_subscription(user_id)
    plan_id = sub["plan_id"] if sub else "free_trial"
    plan    = PLANS.get(plan_id, PLANS["free_trial"])

    used_tokens      = row["total_tokens"] if row else 0
    used_executions  = row["total_executions"] if row else 0
    overage_tokens   = row["overage_tokens"] if row else 0
    overage_cost     = row["overage_cost_cents"] if row else 0

    weekly_tokens    = plan["weekly_tokens"]
    remaining_tokens = None if weekly_tokens is None else max(0, weekly_tokens - used_tokens)

    max_executions        = plan["max_executions_per_week"]
    remaining_executions  = None if max_executions is None else max(0, max_executions - used_executions)

    summary = {
        "week_start":            week_start,
        "plan_id":               plan_id,
        "plan_label":            plan["label"],
        "price_cents":           plan.get("price_cents", 0),
        "overage_allowed":       plan.get("overage_allowed", False),
        "tokens_used":           used_tokens,
        "tokens_limit":          weekly_tokens,
        "tokens_remaining":      remaining_tokens,
        "executions_used":       used_executions,
        "executions_limit":      max_executions,
        "executions_remaining":  remaining_executions,
        "overage_tokens":        overage_tokens,
        "overage_cost_cents":    overage_cost,
    }

    if sub and sub.get("expires_at"):
        summary["trial_ends_at"] = sub["expires_at"]
    if sub is not None:
        summary["payment_verified"] = bool(sub.get("payment_verified"))

    summary["usage_warning"] = None
    if weekly_tokens:
        pct = used_tokens / weekly_tokens
        if pct >= 1.0 and plan.get("overage_allowed"):
            summary["usage_warning"] = {"level": "overage", "pct": round(pct * 100), "message": "Weekly pool used up — extra tokens are being billed at the pay-as-you-go overage rate."}
        elif pct >= 0.9:
            summary["usage_warning"] = {"level": "critical", "pct": round(pct * 100), "message": f"You've used {round(pct*100)}% of your weekly token pool."}
        elif pct >= 0.8:
            summary["usage_warning"] = {"level": "warning", "pct": round(pct * 100), "message": f"You've used {round(pct*100)}% of your weekly token pool."}

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

    summary = get_usage_summary(user_id)
    if summary["tokens_remaining"] is not None and summary["tokens_remaining"] <= 0:
        # Overage-eligible plans keep running (tracked as pay-as-you-go
        # cost, see deduct_usage) instead of hard-blocking.
        if not plan.get("overage_allowed"):
            return False, "Weekly token pool exhausted. Please upgrade your plan."
    if summary["executions_remaining"] is not None and summary["executions_remaining"] <= 0:
        return False, "Weekly execution limit exceeded. Please upgrade your plan."

    return True, "Execution allowed"


# ═══════════════════════════════════════════════════
# USAGE TRACKING
# ═══════════════════════════════════════════════════

def deduct_usage(user_id: str, tokens_used: int, model_name: Optional[str] = None,
                  agent_name: Optional[str] = None, execution_id: Optional[str] = None) -> bool:
    """
    Records tokens against the current week's pool. If this call pushes the
    user past their weekly limit and their plan allows overage, the portion
    past the limit is tracked separately as overage_tokens with its cost
    computed at the tiered pay-as-you-go rate (see module docstring — this
    is tracking only, not live billing, until Stripe is connected).
    """
    init_subs_tables()
    if tokens_used <= 0:
        return True

    now        = datetime.now(timezone.utc)
    week_start = _get_current_week_start()
    record_id  = str(uuid.uuid4())

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO usage_records (id, user_id, tokens_used, model_name, agent_name, execution_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (record_id, user_id, tokens_used, model_name, agent_name, execution_id, now.isoformat()))

        cursor.execute(
            "SELECT total_tokens FROM usage_weekly WHERE user_id = ? AND week_start = ?",
            (user_id, week_start)
        )
        existing = cursor.fetchone()
        tokens_before = existing["total_tokens"] if existing else 0

        # How much of THIS call's tokens land past the plan's weekly pool.
        sub     = get_user_subscription(user_id)
        plan    = PLANS.get(sub["plan_id"], PLANS["free_trial"]) if sub else PLANS["free_trial"]
        pool    = plan.get("weekly_tokens")
        overage_delta = 0
        if pool is not None and plan.get("overage_allowed"):
            tokens_after = tokens_before + tokens_used
            if tokens_after > pool:
                overage_delta = min(tokens_used, tokens_after - pool)
        overage_cost_delta = _overage_cost_cents(overage_delta)

        if existing:
            cursor.execute("""
                UPDATE usage_weekly
                SET total_tokens = total_tokens + ?, total_api_calls = total_api_calls + 1,
                    overage_tokens = overage_tokens + ?, overage_cost_cents = overage_cost_cents + ?
                WHERE user_id = ? AND week_start = ?
            """, (tokens_used, overage_delta, overage_cost_delta, user_id, week_start))
        else:
            cursor.execute("""
                INSERT INTO usage_weekly (user_id, week_start, total_tokens, total_executions, total_api_calls, overage_tokens, overage_cost_cents)
                VALUES (?, ?, ?, 0, 1, ?, ?)
            """, (user_id, week_start, tokens_used, overage_delta, overage_cost_delta))

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


def get_execution_usage(user_id: str, execution_id: str) -> Dict[str, Any]:
    """
    Per-run cost breakdown: every LLM call tagged with this execution_id
    (a goal's thread_id, a workflow run_id, etc.), one row per agent call,
    plus a total. Powers the "what did this run actually cost" view.
    """
    init_subs_tables()
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT agent_name, model_name, tokens_used, timestamp
        FROM usage_records
        WHERE user_id = ? AND execution_id = ?
        ORDER BY timestamp ASC
    """, (user_id, execution_id))
    rows = cursor.fetchall()

    calls = [{
        "agent_name":  r["agent_name"],
        "model_name":  r["model_name"],
        "tokens_used": r["tokens_used"],
        "timestamp":   r["timestamp"],
    } for r in rows]

    return {
        "execution_id":  execution_id,
        "total_tokens":  sum(c["tokens_used"] for c in calls),
        "call_count":    len(calls),
        "calls":         calls,
    }


def record_execution(user_id: str):
    init_subs_tables()
    week_start = _get_current_week_start()

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM usage_weekly WHERE user_id = ? AND week_start = ?", (user_id, week_start))
        if cursor.fetchone():
            cursor.execute("""
                UPDATE usage_weekly SET total_executions = total_executions + 1
                WHERE user_id = ? AND week_start = ?
            """, (user_id, week_start))
        else:
            cursor.execute("""
                INSERT INTO usage_weekly (user_id, week_start, total_tokens, total_executions, total_api_calls, overage_tokens, overage_cost_cents)
                VALUES (?, ?, 0, 1, 0, 0, 0)
            """, (user_id, week_start))
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


@subscription_bp.route("/executions/<execution_id>", methods=["GET"])
@require_auth
def route_execution_usage(execution_id: str):
    """Per-run cost breakdown — one row per agent call, plus a total."""
    user_id = get_current_user_id()
    try:
        return _ok(get_execution_usage(user_id, execution_id))
    except Exception as e:
        return _err(f"Failed to load execution usage: {e}", 500)


@subscription_bp.route("/plans", methods=["GET"])
def route_plans():
    """Public — powers the pricing/upgrade UI. No preamble/internals leaked."""
    return _ok({
        "plans": [
            {
                "id":               plan_id,
                "label":            p["label"],
                "price_cents":      p.get("price_cents", 0),
                "weekly_tokens":    p["weekly_tokens"],
                "overage_allowed":  p.get("overage_allowed", False),
                "features":         sorted(p["features"]),
            }
            for plan_id, p in PLANS.items()
            if plan_id != "executive"   # legacy alias for "max" — don't show it twice
        ],
        "overage_rates": {
            "tier1_per_1k_tokens": OVERAGE_TIER1_RATE_PER_1K,
            "tier1_ceiling":       OVERAGE_TIER1_CEILING,
            "tier2_per_1k_tokens": OVERAGE_TIER2_RATE_PER_1K,
        },
    })


@subscription_bp.route("/upgrade", methods=["POST"])
@require_auth
@rate_limit_user(3, 3600, category="plan_upgrade_abuse")   # 3 plan changes/hour — Stripe isn't wired yet, this is the only abuse brake
def route_upgrade():
    """
    Switches the caller's own plan. Stripe Checkout isn't connected yet
    (see subscription_manager module docstring and stripe_main.py) — every
    activation from here is recorded with payment_verified=False and a
    distinct audit-log event, so it's trivially reconcilable once real
    payment verification lands as the actual gate in front of this.
    """
    user_id = get_current_user_id()
    body    = request.get_json(silent=True) or {}
    plan_id = body.get("plan_id")

    if plan_id not in PLANS:
        return _err(f"Unknown plan_id: {plan_id}")

    try:
        activate_plan(user_id, plan_id, payment_ref=body.get("payment_reference"), payment_verified=False)
        _log_event(user_id, f"plan_upgraded_UNVERIFIED_{plan_id}")
        return _ok({"plan_id": plan_id, "payment_verified": False})
    except Exception as e:
        return _err(f"Upgrade failed: {e}", 500)


@subscription_bp.route("/internal/activate", methods=["POST"])
def route_internal_activate():
    """
    Called by stripe_main.py's webhook handler after a Stripe checkout
    actually clears — NOT reachable from a browser. This is the real
    payment gate: route_upgrade() above always sets payment_verified=False
    and exists only so the tier can be tried pre-Stripe; this is the
    only path that ever sets payment_verified=True.

    stripe_main.py runs as a separate deployable on its own Postgres
    (see database.py) — it has no access to this app's SQLite-backed
    subscription tables, so it calls this over HTTP instead, the same
    way auth-service already hands off to auth.py's /oauth-issue.

    Body: { "user_id": "...", "plan_id": "...", "payment_reference": "..." }
    """
    if request.headers.get("X-Internal-Key") != INTERNAL_SERVICE_KEY:
        return _err("Forbidden", 403)

    body       = request.get_json(silent=True) or {}
    user_id    = body.get("user_id")
    plan_id    = body.get("plan_id")
    payment_ref = body.get("payment_reference")

    if not user_id or not plan_id:
        return _err("user_id and plan_id are required")
    if plan_id not in PLANS:
        return _err(f"Unknown plan_id: {plan_id}")

    try:
        activate_plan(user_id, plan_id, payment_ref=payment_ref, payment_verified=True)
        _log_event(user_id, f"plan_upgraded_VERIFIED_{plan_id}")
        return _ok({"plan_id": plan_id, "payment_verified": True})
    except Exception as e:
        logger.error(f"[Subscription] internal activate failed: {e}")
        return _err(f"Activation failed: {e}", 500)
