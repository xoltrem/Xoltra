"""
supabase_paywall.py — Xoltra Stopper Paywall (Supabase Token Enforcement)

Enforces token-based access control using Supabase as the auth backend.
Replaces the existing subscription_manager.py's local-only enforcement
with a Supabase-backed system that:
- Validates JWT tokens from Supabase Auth
- Checks user tier/plan from Supabase database
- Tracks token usage in Supabase (real-time, cross-device)
- Enforces hard limits with graceful degradation
- Syncs local SQLite usage cache as fallback

Environment variables:
  SUPABASE_URL — Supabase project URL
  SUPABASE_SERVICE_KEY — Supabase service_role key (server-side only)
  SUPABASE_ANON_KEY — Supabase anon key (for client-side JWT validation)
"""
import os
import json
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

import requests

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# ── Tier Definitions ──────────────────────────────────────

TIERS = {
    "free": {
        "name": "Free",
        "daily_tokens": 5000,
        "monthly_tokens": 50000,
        "max_projects": 1,
        "max_workspaces": 0,
        "max_collaborators": 0,
        "features": ["knowledge_base", "pipeline_basic", "qa"],
    },
    "pro": {
        "name": "Pro",
        "daily_tokens": 50000,
        "monthly_tokens": 500000,
        "max_projects": 10,
        "max_workspaces": 3,
        "max_collaborators": 5,
        "features": ["knowledge_base", "pipeline_full", "qa", "projects", "workspaces", "collaboration", "mcp"],
    },
    "team": {
        "name": "Team",
        "daily_tokens": 200000,
        "monthly_tokens": 2000000,
        "max_projects": 50,
        "max_workspaces": 20,
        "max_collaborators": 50,
        "features": ["knowledge_base", "pipeline_full", "qa", "projects", "workspaces", "collaboration", "mcp", "admin", "teams"],
    },
    "enterprise": {
        "name": "Enterprise",
        "daily_tokens": 1000000,
        "monthly_tokens": 10000000,
        "max_projects": -1,  # unlimited
        "max_workspaces": -1,
        "max_collaborators": -1,
        "features": ["knowledge_base", "pipeline_full", "qa", "projects", "workspaces", "collaboration", "mcp", "admin", "teams", "custom_models", "sso"],
    },
}

# ── Supabase Client ───────────────────────────────────────

class SupabaseClient:
    """Minimal Supabase REST client for server-side operations."""

    def __init__(self):
        self.url = SUPABASE_URL.rstrip("/")
        self.service_key = SUPABASE_SERVICE_KEY
        self.anon_key = SUPABASE_ANON_KEY
        self._session = requests.Session()
        self._session.headers.update({
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        })

    @property
    def configured(self) -> bool:
        return bool(self.url and self.service_key)

    def _req(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.url}/rest/v1/{path}"
        return self._session.request(method, url, **kwargs)

    def get_user_tier(self, user_id: str) -> Optional[Dict]:
        """Fetch user's subscription tier from Supabase."""
        if not self.configured:
            return None
        try:
            resp = self._req("GET", f"subscriptions?user_id=eq.{user_id}&select=tier,plan_status,current_period_end,stripe_customer_id")
            if resp.status_code == 200:
                rows = resp.json()
                if rows:
                    return rows[0]
            return None
        except Exception as e:
            logger.warning(f"[Supabase] Failed to fetch tier for {user_id}: {e}")
            return None

    def get_usage(self, user_id: str, period: str = "daily") -> Dict:
        """Get current token usage from Supabase."""
        if not self.configured:
            return {"tokens_used": 0, "requests": 0}
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            resp = self._req(
                "GET",
                f"usage?user_id=eq.{user_id}&date=eq.{today}&select=tokens_used,requests"
            )
            if resp.status_code == 200 and resp.json():
                return resp.json()[0]
            return {"tokens_used": 0, "requests": 0}
        except Exception as e:
            logger.warning(f"[Supabase] Failed to get usage for {user_id}: {e}")
            return {"tokens_used": 0, "requests": 0}

    def record_usage(self, user_id: str, tokens: int, model: str = "", agent: str = "") -> bool:
        """Record token usage in Supabase."""
        if not self.configured:
            return False
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            now = datetime.now(timezone.utc).isoformat()

            # Upsert daily usage
            self._req(
                "POST",
                "usage",
                json={
                    "user_id": user_id,
                    "date": today,
                    "period": "daily",
                    "tokens_used": tokens,
                    "requests": 1,
                    "last_updated": now,
                }
            )

            # Log individual event
            self._req(
                "POST",
                "usage_events",
                json={
                    "user_id": user_id,
                    "tokens": tokens,
                    "model": model,
                    "agent": agent,
                    "created_at": now,
                }
            )
            return {"recorded": True}
        except Exception as e:
            logger.warning(f"[Supabase] Failed to record usage: {e}")
            return {"recorded": False, "error": str(e)}

    def validate_token(self, jwt_token: str) -> Optional[Dict]:
        """Validate a Supabase JWT and return user info."""
        if not self.configured:
            return None
        try:
            resp = requests.get(
                f"{self.url}/auth/v1/user",
                headers={"Authorization": f"Bearer {jwt_token}", "apikey": self.anon_key}
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.warning(f"[Supabase] Token validation failed: {e}")
            return None


# ── Paywall Enforcement ───────────────────────────────────

class PaywallEnforcer:
    """Enforces token limits and feature access based on Supabase tier."""

    def __init__(self):
        self.supabase = SupabaseClient()
        self._local_cache: Dict[str, Dict] = {}  # Fallback when Supabase is down

    def get_user_tier(self, user_id: str) -> str:
        """Get user's current tier, falling back to local cache."""
        if self.supabase.configured:
            tier_data = self.supabase.get_user_tier(user_id)
            if tier_data:
                tier = tier_data.get("tier", "free")
                self._local_cache[user_id] = {"tier": tier, "updated": time.time()}
                return tier

        # Fallback to local cache
        cached = self._local_cache.get(user_id, {})
        return cached.get("tier", "free")

    def check_permission(self, user_id: str, feature: str) -> bool:
        """Check if user has access to a specific feature."""
        tier = self.get_user_tier(user_id)
        tier_config = TIERS.get(tier, TIERS["free"])
        return feature in tier_config["features"]

    def check_token_limit(self, user_id: str, tokens_needed: int) -> Tuple[bool, str]:
        """Check if user has enough tokens remaining. Returns (allowed, reason)."""
        tier = self.get_user_tier(user_id)
        tier_config = TIERS.get(tier, TIERS["free"])
        daily_limit = tier_config["daily_tokens"]

        # Get current usage
        if self.supabase.configured:
            usage = self.supabase.get_usage(user_id, "daily")
            used = usage.get("tokens_used", 0)
        else:
            # Fallback: check local SQLite
            import subscription_manager as sm
            summary = sm.get_usage_summary(user_id)
            used = summary.get("tokens_used_today", 0)

        remaining = daily_limit - used
        if remaining <= 0:
            return False, f"Daily token limit ({daily_limit}) reached. Upgrade to continue."
        if tokens_needed > remaining:
            return False, f"Insufficient tokens: need {tokens_needed}, have {remaining} remaining."

        return True, "ok"

    def deduct_tokens(self, user_id: str, tokens: int, model: str = "", agent: str = "") -> Dict:
        """Deduct tokens from user's balance. Records in Supabase + local."""
        result = {"deducted": tokens, "success": True}

        # Record in Supabase
        if self.supabase.configured:
            sup_result = self.supabase.record_usage(user_id, tokens, model, agent)
            if not sup_result.get("recorded"):
                result["supabase_warning"] = "Failed to record in Supabase"

        # Also record locally for fallback
        try:
            import subscription_manager as sm
            sm.deduct_usage(user_id, tokens, model_name=model, agent_name=agent)
        except Exception as e:
            logger.warning(f"[Paywall] Local deduction failed: {e}")

        return result

    def get_limits(self, user_id: str) -> Dict:
        """Get all limits and current usage for a user."""
        tier = self.get_user_tier(user_id)
        tier_config = TIERS.get(tier, TIERS["free"])

        if self.supabase.configured:
            usage = self.supabase.get_usage(user_id, "daily")
            used = usage.get("tokens_used", 0)
        else:
            import subscription_manager as sm
            summary = sm.get_usage_summary(user_id)
            used = summary.get("tokens_used_today", 0)

        return {
            "tier": tier,
            "tier_name": tier_config["name"],
            "daily_limit": tier_config["daily_tokens"],
            "tokens_used_today": used,
            "tokens_remaining": max(0, tier_config["daily_tokens"] - used),
            "max_projects": tier_config["max_projects"],
            "max_workspaces": tier_config["max_workspaces"],
            "max_collaborators": tier_config["max_collaborators"],
            "features": tier_config["features"],
        }


# ── Singleton ─────────────────────────────────────────────

_enforcer: Optional[PaywallEnforcer] = None


def get_enforcer() -> PaywallEnforcer:
    global _enforcer
    if _enforcer is None:
        _enforcer = PaywallEnforcer()
    return _enforcer


# ── Flask Blueprint ───────────────────────────────────────

from flask import Blueprint, request, jsonify

paywall_bp = Blueprint("paywall", __name__, url_prefix="/api/paywall")


@paywall_bp.route("/limits", methods=["GET"])
def get_limits():
    """Get current user's limits and usage."""
    from auth import require_auth, get_current_user_id
    user_id = get_current_user_id()
    enforcer = get_enforcer()
    return jsonify({"success": True, **enforcer.get_limits(user_id)})


@paywall_bp.route("/check", methods=["POST"])
def check_access():
    """Check if user can perform an action."""
    from auth import require_auth, get_current_user_id
    user_id = get_current_user_id()
    body = request.get_json(silent=True) or {}
    feature = body.get("feature", "")
    tokens = int(body.get("tokens", 0))

    enforcer = get_enforcer()

    if feature:
        has_access = enforcer.check_permission(user_id, feature)
        if not has_access:
            return jsonify({"success": False, "error": f"Feature '{feature}' not available on your plan"}), 403

    if tokens > 0:
        allowed, reason = enforcer.check_token_limit(user_id, tokens)
        if not allowed:
            return jsonify({"success": False, "error": reason}), 402

    return jsonify({"success": True, "allowed": True})


@paywall_bp.route("/upgrade", methods=["GET"])
def upgrade_info():
    """Return available plans and upgrade links."""
    return jsonify({
        "success": True,
        "tiers": {
            name: {
                "name": config["name"],
                "daily_tokens": config["daily_tokens"],
                "features": config["features"],
            }
            for name, config in TIERS.items()
        },
        "upgrade_url": os.getenv("STRIPE_UPGRADE_URL", "/pricing"),
    })


def register_paywall_routes(app):
    app.register_blueprint(paywall_bp)
    logger.info("[Paywall] Supabase paywall routes registered at /api/paywall")