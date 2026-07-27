"""
agent_chain_routes.py — API for custom agent chains + token budgets

    GET    /api/agent-chain/parts     available built-in stages + roles
    GET    /api/agent-chain           current user's chain (detailed)
    PUT    /api/agent-chain           save a chain  {"slots": [...]}
    DELETE /api/agent-chain           reset to default
    GET    /api/agent-chain/budget    projected per-agent token allowances

Registered from app.py via register_agent_chain_routes(app).
"""

import logging

from flask import Blueprint, request, jsonify

import agent_chain as ac
import token_budget as tb
from auth import require_auth, get_current_user_id

logger = logging.getLogger(__name__)

agent_chain_bp = Blueprint("agent_chain", __name__, url_prefix="/api/agent-chain")


def _err(msg, status=400):
    return jsonify({"success": False, "error": msg}), status


def _ok(data):
    return jsonify({"success": True, **data})


@agent_chain_bp.route("/parts", methods=["GET"])
@require_auth
def route_parts():
    return _ok({"parts": ac.available_parts()})


@agent_chain_bp.route("", methods=["GET"])
@require_auth
def route_get_chain():
    try:
        return _ok({"chain": ac.get_chain_detail(get_current_user_id())})
    except Exception as e:
        logger.error(f"[AgentChain] get failed: {e}")
        return _err("Failed to load agent chain", 500)


@agent_chain_bp.route("", methods=["PUT", "POST"])
@require_auth
def route_save_chain():
    body  = request.get_json(silent=True) or {}
    slots = body.get("slots", body.get("chain"))
    if slots is None:
        return _err("Body must include 'slots'")
    try:
        ac.save_chain(get_current_user_id(), slots)
        return _ok({"chain": ac.get_chain_detail(get_current_user_id())})
    except ac.ChainError as e:
        return _err(str(e))
    except Exception as e:
        logger.error(f"[AgentChain] save failed: {e}")
        return _err("Failed to save agent chain", 500)


@agent_chain_bp.route("", methods=["DELETE"])
@require_auth
def route_reset_chain():
    try:
        ac.reset_chain(get_current_user_id())
        return _ok({"chain": ac.get_chain_detail(get_current_user_id())})
    except Exception as e:
        logger.error(f"[AgentChain] reset failed: {e}")
        return _err("Failed to reset agent chain", 500)


@agent_chain_bp.route("/budget", methods=["GET"])
@require_auth
def route_budget():
    """What each agent in the chain is allowed to spend on the next run."""
    user_id = get_current_user_id()
    try:
        rb = tb.budget_for_user(user_id)
        report = rb.report()
        report["agents"] = [
            {**a, "label": ac.slot_label(a["slot"])} for a in report["agents"]
        ]
        return _ok({"budget": report})
    except Exception as e:
        logger.error(f"[AgentChain] budget failed: {e}")
        return _err("Failed to compute token budget", 500)


def register_agent_chain_routes(app):
    ac.init_agent_chain_tables()
    app.register_blueprint(agent_chain_bp)
    logger.info("[AgentChain] routes registered")
