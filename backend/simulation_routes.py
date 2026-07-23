"""
simulation_routes.py — Xoltra Simulation API Endpoints
Register with Flask by calling register_simulation_routes(app) in app.py.

Endpoints added:
  GET  /api/simulation/status
  POST /api/simulation/graph
  POST /api/simulation/workflow
  POST /api/simulation/pipeline
  POST /api/simulation/mutate
  POST /api/simulation/compact-view
  GET  /api/simulation/stats-view
  POST /api/simulation/event          ← Unity → Python event ingress

Add to app.py (after kdb.init_storage()):
    from simulation_routes import register_simulation_routes
    register_simulation_routes(app)
    unity_bridge.start_bridge()
"""

import logging
import traceback

from flask import Blueprint, request, jsonify
import unity_bridge as bridge
import simulation_engine as sim
from simulation_types import SimCommand

logger = logging.getLogger(__name__)

_sim_bp = Blueprint("simulation", __name__, url_prefix="/api/simulation")


def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


def _ok(data: dict):
    return jsonify({"success": True, **data})


# ─── Status ───────────────────────────────────────────────────────────────────

@_sim_bp.route("/status", methods=["GET"])
def simulation_status():
    """Returns bridge connection status. Frontend polls this to show the Unity badge."""
    return _ok(bridge.get_status())


# ─── Knowledge Graph ──────────────────────────────────────────────────────────

@_sim_bp.route("/graph", methods=["POST"])
def render_graph():
    """
    Visualise the knowledge graph for a given user input.
    Body: { "message": str, "mode": "fast"|"thinking" }
    """
    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    mode    = body.get("mode", "thinking")

    if not message:
        return _err("message is required")
    if mode not in ("fast", "thinking"):
        mode = "thinking"

    try:
        sim.visualise_knowledge_graph(message, mode=mode)
        return _ok({"queued": True, "mode": mode})
    except Exception as e:
        logger.error(f"[/simulation/graph] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


# ─── Workflow ─────────────────────────────────────────────────────────────────

@_sim_bp.route("/workflow", methods=["POST"])
def render_workflow():
    """
    Visualise a workflow blueprint.
    Body: { "blueprint": {...ArchitectAgent output...}, "goal": str }
    """
    body      = request.get_json(silent=True) or {}
    blueprint = body.get("blueprint")
    goal      = (body.get("goal") or "").strip()

    if not isinstance(blueprint, dict):
        return _err("blueprint must be an object")

    try:
        sim.visualise_workflow(blueprint, goal)
        return _ok({"queued": True})
    except Exception as e:
        logger.error(f"[/simulation/workflow] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


@_sim_bp.route("/workflow/advance", methods=["POST"])
def advance_phase():
    """Body: { "phase_index": int }"""
    body = request.get_json(silent=True) or {}
    idx  = body.get("phase_index", 0)
    sim.advance_workflow_phase(int(idx))
    return _ok({"queued": True})


@_sim_bp.route("/workflow/complete-step", methods=["POST"])
def complete_step():
    """Body: { "phase_index": int, "step_index": int }"""
    body = request.get_json(silent=True) or {}
    sim.complete_workflow_step(int(body.get("phase_index", 0)),
                               int(body.get("step_index", 0)))
    return _ok({"queued": True})


# ─── Agent Pipeline ───────────────────────────────────────────────────────────

@_sim_bp.route("/pipeline", methods=["POST"])
def render_pipeline():
    """
    Animate agent pipeline execution.
    Body: { "tier": str, "agents": [str], "step_outputs": {agent: preview} }
    """
    body         = request.get_json(silent=True) or {}
    tier         = body.get("tier", "medium")
    agents       = body.get("agents", [])
    step_outputs = body.get("step_outputs", {})

    if not agents:
        # Auto-derive from llm module
        try:
            from llm import get_active_tier, get_active_agents
            info   = get_active_tier()
            tier   = info["complexity"]
            agents = info["agents"]
        except Exception:
            return _err("agents list required if not auto-derived")

    try:
        sim.playback_pipeline_run(tier, list(agents), step_outputs)
        return _ok({"queued": True, "agents": list(agents), "tier": tier})
    except Exception as e:
        logger.error(f"[/simulation/pipeline] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


# ─── Data Mutation ────────────────────────────────────────────────────────────

@_sim_bp.route("/mutate", methods=["POST"])
def render_mutation():
    """
    Visualise before/after data mutation.
    Body: { "label": str, "before": {}, "after": {} }
    """
    body   = request.get_json(silent=True) or {}
    label  = (body.get("label") or "Data Object").strip()
    before = body.get("before")
    after  = body.get("after")

    if not isinstance(before, dict) or not isinstance(after, dict):
        return _err("before and after must be objects")

    try:
        sim.visualise_data_mutation(label, before, after)
        return _ok({"queued": True})
    except Exception as e:
        logger.error(f"[/simulation/mutate] {e}\n{traceback.format_exc()}")
        return _err(str(e), 500)


# ─── Session Compact View ─────────────────────────────────────────────────────

@_sim_bp.route("/compact-view", methods=["POST"])
def compact_view():
    """
    Animate a newly-compacted knowledge node appearing in Unity.
    Body: same as compact_session() return value — node_id, node_type, title, summary
    """
    body = request.get_json(silent=True) or {}
    try:
        sim.visualise_session_compact(body)
        return _ok({"queued": True})
    except Exception as e:
        return _err(str(e), 500)


# ─── Stats Overview ───────────────────────────────────────────────────────────

@_sim_bp.route("/stats-view", methods=["GET"])
def stats_view():
    """Render the full knowledge galaxy overview."""
    try:
        sim.visualise_knowledge_stats()
        return _ok({"queued": True})
    except Exception as e:
        return _err(str(e), 500)


# ─── Unity → Python Event Ingress ─────────────────────────────────────────────

@_sim_bp.route("/event", methods=["POST"])
def receive_event():
    """
    HTTP fallback for Unity→Python events (used when WebSocket isn't available).
    Body: { "type": "node_clicked", "payload": {...} }
    """
    body       = request.get_json(silent=True) or {}
    event_type = body.get("type", "")
    payload    = body.get("payload", {})

    if not event_type:
        return _err("type is required")

    # Dispatch through the same handler registry as WebSocket events
    from unity_bridge import _event_handlers
    handlers = _event_handlers.get(event_type, [])
    for fn in handlers:
        try:
            fn(payload)
        except Exception as e:
            logger.warning(f"[/simulation/event] handler error: {e}")

    return _ok({"dispatched": len(handlers)})


# ─── Registration ─────────────────────────────────────────────────────────────

def register_simulation_routes(app):
    """Call this in app.py after creating the Flask app."""
    app.register_blueprint(_sim_bp)
    logger.info("[Simulation] Routes registered under /api/simulation")
