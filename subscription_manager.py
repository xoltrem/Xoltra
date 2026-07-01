"""
subscription_manager.py — Xoltra Subscription & Usage Tracking

Centralized service for managing multi-tenant subscription tiers,
enforcing limits, checking feature access, and recording usage.
"""

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import knowledge_db as kdb

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════
# PLAN DEFINITIONS
# ═══════════════════════════════════════════════════

ALL_AGENTS = {
    "router", "clarifier", "architect", "critic", "operator", 
    "validator", "compiler", "knowledge_retriever", "workflow_builder",
    "qa", "researcher", "document_processor"
}

ALL_TOOLS = {"web_search", "code_executor", "database_query", "api_caller", "file_system"}
BASIC_TOOLS = {"web_search"}
STANDARD_TOOLS = {"web_search", "file_system"}

ALL_FEATURES = {"knowledge_engine", "workflow_builder", "simulation", "document_pipeline", "qa"}

PLANS = {
    "free_trial": {
        "label": "Free Trial",
        "monthly_tokens": 5_000,
        "context_window": 8_000,
        "max_executions_per_month": 20,
        "max_workflows": 3,
        "max_knowledge_nodes": 50,
        "allowed_tiers": {"simple", "medium", "complex"},
        "allowed_agents": ALL_AGENTS,
        "allowed_tools": ALL_TOOLS,
        "features": {"knowledge_engine", "workflow_builder", "simulation", "document_pipeline", "qa"},
        "trial_days": 14,
    },
    "basic": {
        "label": "Basic",
        "monthly_tokens": 50_000,
        "context_window": 8_000,
        "max_executions_per_month": 100,
        "max_workflows": 10,
        "max_knowledge_nodes": 200,
        "allowed_tiers": {"simple", "medium"},
        "allowed_agents": {"router", "clarifier", "architect", "critic", "validator", "compiler", "qa"},
        "allowed_tools": BASIC_TOOLS,
        "features": {"qa", "document_pipeline"},
    },
    "standard": {
        "label": "Standard",
        "monthly_tokens": 150_000,
        "context_window": 10_000,
        "max_executions_per_month": 500,
        "max_workflows": 50,
        "max_knowledge_nodes": 1000,
        "allowed_tiers": {"simple", "medium", "complex"},
        "allowed_agents": {"router", "clarifier", "architect", "critic", "operator", "validator", "compiler", "qa", "knowledge_retriever"},
        "allowed_tools": STANDARD_TOOLS,
        "features": {"qa", "document_pipeline", "knowledge_engine", "workflow_builder"},
    },
    "premium": {
        "label": "Premium",
        "monthly_tokens": 500_000,
        "context_window": 32_000,
        "max_executions_per_month": 2000,
        "max_workflows": 200,
        "max_knowledge_nodes": 5000,
        "allowed_tiers": {"simple", "medium", "complex"},
        "allowed_agents": ALL_AGENTS,
        "allowed_tools": ALL_TOOLS,
        "features": ALL_FEATURES,
    },
    "enterprise": {
        "label": "Enterprise",
        "monthly_tokens": None,           # Unlimited — pay-as-you-go
        "context_window": 32_000,
        "max_executions_per_month": None, # Unlimited
        "max_workflows": None,
        "max_knowledge_nodes": None,
        "allowed_tiers": {"simple", "medium", "complex"},
        "allowed_agents": ALL_AGENTS,
        "allowed_tools": ALL_TOOLS,
        "features": ALL_FEATURES,
    },
}

_subs_tables_created = False

def init_subs_tables():
    """Create subscription and usage tables."""
    global _subs_tables_created
    if _subs_tables_created:
        return

    conn = kdb._get_conn()
    cursor = conn.cursor()
    
    # Subscriptions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        user_id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL,
        status TEXT NOT NULL,
        activated_at TEXT NOT NULL,
        expires_at TEXT,
        payment_reference TEXT
    )
    """)
    
    # Granular usage records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usage_records (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        tokens_used INTEGER NOT NULL,
        model_name TEXT,
        agent_name TEXT,
        execution_id TEXT,
        timestamp TEXT NOT NULL
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_user_time ON usage_records(user_id, timestamp)")
    
    # Monthly aggregation
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usage_monthly (
        user_id TEXT NOT NULL,
        month TEXT NOT NULL,
        total_tokens INTEGER DEFAULT 0,
        total_executions INTEGER DEFAULT 0,
        total_api_calls INTEGER DEFAULT 0,
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
    """Activate the Free Trial plan for a new user."""
    init_subs_tables()
    
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=PLANS["free_trial"]["trial_days"])
    
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO subscriptions (user_id, plan_id, status, activated_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, "free_trial", "active", now.isoformat(), expires.isoformat()))
    conn.commit()
    
    logger.info(f"[SubscriptionManager] Trial activated for user: {user_id}")
    return True

def activate_plan(user_id: str, plan_id: str, payment_ref: str = None) -> bool:
    """Activate a paid plan for a user."""
    if plan_id not in PLANS:
        raise ValueError(f"Unknown plan_id: {plan_id}")
        
    init_subs_tables()
    
    now = datetime.now(timezone.utc)
    
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO subscriptions (user_id, plan_id, status, activated_at, expires_at, payment_reference)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, plan_id, "active", now.isoformat(), None, payment_ref))
    
    # Reset monthly usage on plan change
    month_str = _get_current_month_str()
    cursor.execute("""
        INSERT OR REPLACE INTO usage_monthly (user_id, month, total_tokens, total_executions, total_api_calls)
        VALUES (?, ?, 0, 0, 0)
    """, (user_id, month_str))
    
    conn.commit()
    
    logger.info(f"[SubscriptionManager] Plan '{plan_id}' activated for user: {user_id}")
    return True

# ═══════════════════════════════════════════════════
# QUERIES
# ═══════════════════════════════════════════════════

def get_user_subscription(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve the user's active subscription."""
    init_subs_tables()
    
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT plan_id, status, activated_at, expires_at FROM subscriptions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        return None
        
    return {
        "plan_id": row["plan_id"],
        "status": row["status"],
        "activated_at": row["activated_at"],
        "expires_at": row["expires_at"]
    }

def get_usage_summary(user_id: str) -> Dict[str, Any]:
    """Get the usage summary for the current month."""
    init_subs_tables()
    
    month_str = _get_current_month_str()
    
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT total_tokens, total_executions 
        FROM usage_monthly 
        WHERE user_id = ? AND month = ?
    """, (user_id, month_str))
    
    row = cursor.fetchone()
    
    sub = get_user_subscription(user_id)
    plan_id = sub["plan_id"] if sub else "free_trial"
    plan = PLANS.get(plan_id, PLANS["free_trial"])
    
    used_tokens = row["total_tokens"] if row else 0
    used_executions = row["total_executions"] if row else 0
    
    monthly_tokens = plan["monthly_tokens"]
    remaining_tokens = None
    if monthly_tokens is not None:
        remaining_tokens = max(0, monthly_tokens - used_tokens)
        
    max_executions = plan["max_executions_per_month"]
    remaining_executions = None
    if max_executions is not None:
        remaining_executions = max(0, max_executions - used_executions)
        
    return {
        "month": month_str,
        "plan_id": plan_id,
        "tokens_used": used_tokens,
        "tokens_limit": monthly_tokens,
        "tokens_remaining": remaining_tokens,
        "executions_used": used_executions,
        "executions_limit": max_executions,
        "executions_remaining": remaining_executions
    }

def get_remaining_tokens(user_id: str) -> Optional[int]:
    """Get remaining tokens for the month. None if unlimited."""
    summary = get_usage_summary(user_id)
    return summary["tokens_remaining"]

def get_context_window(user_id: str) -> int:
    """Get the max context window allowed by the user's plan."""
    sub = get_user_subscription(user_id)
    plan_id = sub["plan_id"] if sub else "free_trial"
    return PLANS.get(plan_id, PLANS["free_trial"])["context_window"]

# ═══════════════════════════════════════════════════
# ACCESS CONTROL
# ═══════════════════════════════════════════════════

def check_permission(user_id: str, feature: str) -> bool:
    """Check if the user's plan includes a specific feature."""
    sub = get_user_subscription(user_id)
    if not sub or sub["status"] != "active":
        return False
        
    plan = PLANS.get(sub["plan_id"])
    if not plan:
        return False
        
    return feature in plan["features"]

def check_agent_access(user_id: str, agent_name: str) -> bool:
    """Check if the user's plan allows access to a specific agent."""
    sub = get_user_subscription(user_id)
    if not sub or sub["status"] != "active":
        return False
        
    plan = PLANS.get(sub["plan_id"])
    if not plan:
        return False
        
    return agent_name.lower() in [a.lower() for a in plan["allowed_agents"]]

def check_tool_access(user_id: str, tool_name: str) -> bool:
    """Check if the user's plan allows access to a specific tool."""
    sub = get_user_subscription(user_id)
    if not sub or sub["status"] != "active":
        return False
        
    plan = PLANS.get(sub["plan_id"])
    if not plan:
        return False
        
    return tool_name in plan["allowed_tools"]

def can_execute(user_id: str) -> tuple[bool, str]:
    """Pre-flight check: Can this user execute a pipeline?"""
    sub = get_user_subscription(user_id)
    if not sub:
        return False, "No active subscription found"
        
    if sub["status"] != "active":
        return False, f"Subscription is {sub['status']}"
        
    if sub["expires_at"]:
        expiry = datetime.fromisoformat(sub["expires_at"])
        if datetime.now(timezone.utc) > expiry:
            return False, "Subscription has expired"
            
    summary = get_usage_summary(user_id)
    
    if summary["tokens_remaining"] is not None and summary["tokens_remaining"] <= 0:
        return False, "Monthly token limit exceeded. Please upgrade your plan."
        
    if summary["executions_remaining"] is not None and summary["executions_remaining"] <= 0:
        return False, "Monthly execution limit exceeded. Please upgrade your plan."
        
    return True, "Execution allowed"

# ═══════════════════════════════════════════════════
# USAGE TRACKING
# ═══════════════════════════════════════════════════

def deduct_usage(user_id: str, tokens_used: int, model_name: str = None, agent_name: str = None, execution_id: str = None) -> bool:
    """Record token usage and update monthly aggregates."""
    init_subs_tables()
    
    if tokens_used <= 0:
        return True
        
    now = datetime.now(timezone.utc)
    month_str = _get_current_month_str()
    record_id = str(uuid.uuid4())
    
    conn = kdb._get_conn()
    cursor = conn.cursor()
    
    try:
        # 1. Insert granular record
        cursor.execute("""
            INSERT INTO usage_records (id, user_id, tokens_used, model_name, agent_name, execution_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (record_id, user_id, tokens_used, model_name, agent_name, execution_id, now.isoformat()))
        
        # 2. Update monthly aggregate
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

def record_execution(user_id: str):
    """Record a completed workflow execution."""
    init_subs_tables()
    month_str = _get_current_month_str()
    
    conn = kdb._get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM usage_monthly WHERE user_id = ? AND month = ?", (user_id, month_str))
        if cursor.fetchone():
            cursor.execute("""
                UPDATE usage_monthly 
                SET total_executions = total_executions + 1
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
