"""
simulation_engine.py — Xoltra Unity Simulation Engine
Translates AI pipeline outputs into ordered SimCommand sequences
and dispatches them through unity_bridge.

Public methods (all called from Flask routes or pipeline hooks):
  visualise_knowledge_graph(user_input)
  visualise_workflow(blueprint, goal)
  visualise_agent_pipeline(tier, agents)
  visualise_data_mutation(obj_label, before, after)
  visualise_session_compact(node_result)
  playback_pipeline_run(tier, step_callback)

Every method is non-blocking: it returns immediately after queuing
all commands. Unity renders them at ~60 Hz.
"""

import logging
import math
import threading
from typing import Dict, List, Optional, Callable, Any

import knowledge_db as kdb
import unity_bridge as bridge
from simulation_types import SimCommand, NODE_COLORS, CommandType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# LAYOUT HELPERS
# ═══════════════════════════════════════════════════

def _ring_positions(n: int, radius: float = 4.0, z: float = 0.0) -> List[Dict]:
    """Evenly space n nodes around a circle."""
    positions = []
    for i in range(n):
        angle = (2 * math.pi * i) / max(n, 1)
        positions.append({
            "x": round(radius * math.cos(angle), 3),
            "y": round(radius * math.sin(angle), 3),
            "z": z,
        })
    return positions


def _grid_positions(n: int, cols: int = 4, spacing: float = 3.0) -> List[Dict]:
    """Left-to-right grid layout."""
    positions = []
    for i in range(n):
        col = i % cols
        row = i // cols
        positions.append({
            "x": round(col * spacing - (cols * spacing / 2), 3),
            "y": round(-row * spacing, 3),
            "z": 0.0,
        })
    return positions


def _pipeline_positions(agents: List[str]) -> List[Dict]:
    """Horizontal left-to-right pipeline layout."""
    spacing = 2.8
    total_w = spacing * (len(agents) - 1)
    return [
        {"x": round(i * spacing - total_w / 2, 3), "y": 0.0, "z": 0.0}
        for i in range(len(agents))
    ]


# ═══════════════════════════════════════════════════
# KNOWLEDGE GRAPH VISUALISATION
# ═══════════════════════════════════════════════════

def visualise_knowledge_graph(user_input: str, mode: str = "thinking"):
    """
    Retrieve relevant nodes from the knowledge base and render them
    as an interactive 3D graph in Unity.

    Sends: clear_scene → render_node × N → render_edge × M → highlight_path
    """
    from xoltra_knowledge_engine import get_context_by_mode
    nodes = get_context_by_mode(user_input, mode=mode)

    if not nodes:
        bridge.send(SimCommand.show_toast("Knowledge base is empty", "info"))
        return

    cmds: List[SimCommand] = [
        SimCommand.clear_scene(),
        SimCommand.update_status_bar("Loading knowledge graph…", 0.1),
    ]

    positions = _ring_positions(len(nodes), radius=max(3.5, len(nodes) * 0.6))

    # Render nodes
    id_to_idx: Dict[str, int] = {}
    for idx, node in enumerate(nodes):
        node_id   = node["id"]
        node_type = node.get("type", "insight")
        content   = node.get("content", {})
        relevance = node.get("relevance", 0.5)

        label   = _label_from_node(node_type, content)
        summary = _summary_from_node(node_type, content)

        cmds.append(SimCommand.render_node(
            node_id=node_id,
            node_type=node_type,
            label=label,
            summary=summary,
            position=positions[idx],
            relevance=relevance,
        ))
        id_to_idx[node_id] = idx

    cmds.append(SimCommand.update_status_bar("Fetching edges…", 0.6))

    # Render edges for nodes we have
    seen_edges = set()
    for node in nodes:
        try:
            edges = kdb.get_node_edges(node["id"], direction="outgoing")
        except Exception:
            continue
        for edge in edges:
            to_id = edge.get("to_node", "")
            if to_id not in id_to_idx:
                continue
            key = (node["id"], to_id)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            cmds.append(SimCommand.render_edge(
                from_id   = node["id"],
                to_id     = to_id,
                edge_type = edge.get("edge_type", "relates_to"),
                strength  = edge.get("strength", 0.5),
                label     = edge.get("reason", "")[:30],
            ))

    # Highlight the highest-relevance node
    primary = max(nodes, key=lambda n: n.get("relevance", 0), default=None)
    if primary:
        cmds.append(SimCommand.highlight_node(primary["id"], pulse=True))

    cmds.append(SimCommand.update_status_bar("Graph ready", 1.0))
    cmds.append(SimCommand.show_toast(
        f"{len(nodes)} nodes · {len(seen_edges)} edges", "success"
    ))

    bridge.send_many(cmds)
    logger.info(f"[Sim] Knowledge graph: {len(nodes)} nodes, {len(seen_edges)} edges")


def _label_from_node(node_type: str, content: dict) -> str:
    if node_type == "goal":
        return (content.get("title") or content.get("clarified_goal", "Goal"))[:50]
    if node_type == "workflow":
        phases = content.get("phases", [])
        return f"Workflow ({len(phases)} phases)"
    if node_type == "insight":
        return (content.get("title") or "Insight")[:50]
    if node_type == "document":
        return "Document"
    return node_type.title()[:50]


def _summary_from_node(node_type: str, content: dict) -> str:
    if node_type == "goal":
        return (content.get("clarified_goal") or content.get("session_summary", ""))[:180]
    if node_type == "workflow":
        return content.get("goal_summary", "")[:180]
    if node_type == "insight":
        return (content.get("pattern") or "")[:180]
    if node_type == "document":
        return content.get("extracted_goal", "")[:180]
    return ""


# ═══════════════════════════════════════════════════
# WORKFLOW VISUALISATION
# ═══════════════════════════════════════════════════

def visualise_workflow(blueprint: dict, goal: str = ""):
    """
    Render an ArchitectAgent blueprint as an interactive phase/step graph.

    Sends: clear_scene → render_workflow → show_toast
    """
    if not blueprint.get("phases"):
        bridge.send(SimCommand.show_toast("No workflow data to visualise", "warning"))
        return

    cmds = [
        SimCommand.clear_scene(),
        SimCommand.update_status_bar("Rendering workflow…", 0.2),
        SimCommand.render_workflow(blueprint),
        SimCommand.update_status_bar(goal[:60] or "Workflow ready", 1.0),
        SimCommand.show_toast(
            f"{len(blueprint['phases'])} phases · "
            f"{sum(len(p.get('steps',[])) for p in blueprint['phases'])} steps",
            "success"
        ),
    ]
    bridge.send_many(cmds)
    logger.info(f"[Sim] Workflow: {len(blueprint['phases'])} phases")


def advance_workflow_phase(phase_index: int):
    """Mark a phase as active (call as the user works through it)."""
    bridge.send(SimCommand(
        type=CommandType.ADVANCE_PHASE,
        payload={"phase_index": phase_index},
    ))


def complete_workflow_step(phase_index: int, step_index: int):
    """Mark a step as done."""
    bridge.send(SimCommand(
        type=CommandType.COMPLETE_STEP,
        payload={"phase_index": phase_index, "step_index": step_index},
    ))


# ═══════════════════════════════════════════════════
# AGENT PIPELINE VISUALISATION
# ═══════════════════════════════════════════════════

def visualise_agent_pipeline(tier: str, agents: List[str]):
    """
    Render the agent pipeline as a horizontal node graph.
    All agents shown as pending; use activate_agent / complete_agent
    to animate execution in real-time.
    """
    cmds = [
        SimCommand.clear_scene(),
        SimCommand.render_pipeline(agents, tier),
        SimCommand.update_status_bar(f"Pipeline ready ({tier.upper()})", 1.0),
    ]
    bridge.send_many(cmds)
    logger.info(f"[Sim] Pipeline: {tier} tier, {len(agents)} agents")


def playback_pipeline_run(
    tier: str,
    agents: List[str],
    step_outputs: Optional[Dict[str, str]] = None,
    delay_secs: float = 0.4,
):
    """
    Animate pipeline execution sequentially in a background thread.
    step_outputs: { agent_name: preview_string } — shown as tooltips.
    """
    outputs = step_outputs or {}

    def _run():
        visualise_agent_pipeline(tier, agents)
        import time
        time.sleep(0.5)
        for agent in agents:
            bridge.send(SimCommand.activate_agent(agent))
            bridge.send(SimCommand.update_status_bar(f"Running: {agent}", -1))
            time.sleep(delay_secs)
            bridge.send(SimCommand.complete_agent(agent, outputs.get(agent, "")))
        bridge.send(SimCommand.update_status_bar("Pipeline complete", 1.0))
        bridge.send(SimCommand.show_toast("All agents finished", "success"))

    threading.Thread(target=_run, daemon=True).start()


# ═══════════════════════════════════════════════════
# DATA MUTATION VISUALISATION
# ═══════════════════════════════════════════════════

def visualise_data_mutation(
    obj_label: str,
    before: dict,
    after: dict,
    obj_id: Optional[str] = None,
):
    """
    Spawn a data object, then animate field-level mutations (before → after).
    Used when the AI modifies source data so the user can see exactly what changed.

    before / after: flat or nested dicts — nested keys shown as "parent.child"
    """
    import uuid as _uuid
    oid = obj_id or str(_uuid.uuid4())[:8]

    cmds: List[SimCommand] = [
        SimCommand.clear_scene(),
        SimCommand.load_data_object(oid, before, obj_label),
        SimCommand.update_status_bar("Showing data mutations…", 0.1),
    ]

    diffs = _diff_dicts(before, after)
    for i, (path, old_val, new_val) in enumerate(diffs):
        progress = 0.1 + 0.85 * ((i + 1) / max(len(diffs), 1))
        cmds.append(SimCommand.mutate_field(oid, path, old_val, new_val))
        cmds.append(SimCommand.update_status_bar(f"Mutating: {path}", round(progress, 2)))

    cmds.append(SimCommand.update_status_bar(f"{len(diffs)} fields changed", 1.0))
    cmds.append(SimCommand.show_toast(f"{len(diffs)} mutations applied", "success"))
    bridge.send_many(cmds)
    logger.info(f"[Sim] Data mutation: {len(diffs)} diffs on '{obj_label}'")


def _diff_dicts(
    before: dict,
    after: dict,
    prefix: str = "",
) -> List[tuple]:
    """Recursively diff two dicts → [(path, old_val, new_val)]."""
    diffs = []
    all_keys = set(before) | set(after)
    for key in all_keys:
        path = f"{prefix}.{key}" if prefix else key
        b_val = before.get(key)
        a_val = after.get(key)
        if isinstance(b_val, dict) and isinstance(a_val, dict):
            diffs.extend(_diff_dicts(b_val, a_val, path))
        elif b_val != a_val:
            diffs.append((path, b_val, a_val))
    return diffs


# ═══════════════════════════════════════════════════
# SESSION COMPACTION VISUALISATION
# ═══════════════════════════════════════════════════

def visualise_session_compact(compact_result: dict):
    """
    After a session is saved to the knowledge base, animate the new node
    appearing and linking into the graph.

    compact_result: return value of xke.compact_session()
    """
    if not compact_result:
        return

    node_id   = compact_result.get("node_id", "new")
    node_type = compact_result.get("node_type", "insight")
    title     = compact_result.get("title", "New Node")
    summary   = compact_result.get("summary", "")

    cmds = [
        SimCommand.render_node(
            node_id=node_id,
            node_type=node_type,
            label=title,
            summary=summary,
            position={"x": 0, "y": 0, "z": 0},
            relevance=1.0,
        ),
        SimCommand.highlight_node(node_id, color=NODE_COLORS[node_type], pulse=True),
        SimCommand.show_toast(f"Saved: {title[:60]}", "success"),
    ]
    bridge.send_many(cmds)


# ═══════════════════════════════════════════════════
# FULL STATS OVERVIEW
# ═══════════════════════════════════════════════════

def visualise_knowledge_stats():
    """
    Render all active nodes as a galaxy-style overview —
    types clustered together, sized by access_count.
    """
    try:
        stats = kdb.get_stats()
    except Exception as e:
        bridge.send(SimCommand.show_toast(f"Stats unavailable: {e}", "error"))
        return

    cmds: List[SimCommand] = [
        SimCommand.clear_scene(),
        SimCommand.update_status_bar("Building knowledge galaxy…", 0.1),
    ]

    type_order = ["goal", "workflow", "insight", "document"]
    cluster_radius = 5.0
    type_positions = _ring_positions(len(type_order), radius=cluster_radius)

    for t_idx, node_type in enumerate(type_order):
        count = stats.get("nodes_by_type", {}).get(node_type, 0)
        if count == 0:
            continue

        center = type_positions[t_idx]
        nodes  = kdb.get_nodes_by_type(node_type, status="active")

        # Cluster nodes around their type center
        offsets = _ring_positions(len(nodes), radius=1.8)
        for n_idx, node in enumerate(nodes):
            pos = {
                "x": round(center["x"] + offsets[n_idx]["x"], 3),
                "y": round(center["y"] + offsets[n_idx]["y"], 3),
                "z": 0.0,
            }
            cmds.append(SimCommand.render_node(
                node_id   = node["id"],
                node_type = node_type,
                label     = _label_from_node(node_type, node.get("content", {})),
                summary   = _summary_from_node(node_type, node.get("content", {})),
                position  = pos,
                relevance = min(node.get("access_count", 0) / 10.0, 1.0),
            ))

    total = stats.get("total_nodes", 0)
    cmds.append(SimCommand.update_status_bar(
        f"{total} nodes · {stats.get('total_edges',0)} edges · "
        f"{stats.get('vector_count',0)} vectors", 1.0
    ))
    bridge.send_many(cmds)
    logger.info(f"[Sim] Stats galaxy: {total} nodes")
