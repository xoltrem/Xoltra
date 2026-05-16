"""
simulation_types.py — Xoltra Unity Simulation Protocol
Defines every command and event that crosses the Python ↔ Unity WebSocket.

Command flow:
  Python (simulation_engine) → unity_bridge → Unity (XoltraSimManager)

Event flow:
  Unity (user interaction) → unity_bridge → Flask /api/simulation/event

All messages are JSON with shape: { "type": str, "id": str, "payload": dict }
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid
import json


# ═══════════════════════════════════════════════════
# COMMAND TYPES  (Python → Unity)
# ═══════════════════════════════════════════════════

class CommandType(str, Enum):
    # Scene control
    CLEAR_SCENE          = "clear_scene"
    SET_CAMERA           = "set_camera"

    # Node graph (knowledge base)
    RENDER_NODE          = "render_node"
    UPDATE_NODE          = "update_node"
    REMOVE_NODE          = "remove_node"
    RENDER_EDGE          = "render_edge"
    HIGHLIGHT_NODE       = "highlight_node"
    HIGHLIGHT_PATH       = "highlight_path"

    # Workflow visualisation
    RENDER_WORKFLOW      = "render_workflow"
    ADVANCE_PHASE        = "advance_phase"
    COMPLETE_STEP        = "complete_step"
    SET_PHASE_STATUS     = "set_phase_status"

    # Agent pipeline visualisation
    RENDER_PIPELINE      = "render_pipeline"
    ACTIVATE_AGENT       = "activate_agent"
    COMPLETE_AGENT       = "complete_agent"
    AGENT_ERROR          = "agent_error"
    SHOW_AGENT_OUTPUT    = "show_agent_output"

    # Data manipulation (Feature 3 core)
    LOAD_DATA_OBJECT     = "load_data_object"
    MUTATE_FIELD         = "mutate_field"
    ANIMATE_TRANSFORM    = "animate_transform"
    SHOW_DIFF            = "show_diff"

    # UI overlays
    SHOW_TOAST           = "show_toast"
    SHOW_MODAL           = "show_modal"
    UPDATE_STATUS_BAR    = "update_status_bar"


# ═══════════════════════════════════════════════════
# EVENT TYPES  (Unity → Python)
# ═══════════════════════════════════════════════════

class EventType(str, Enum):
    NODE_CLICKED         = "node_clicked"
    NODE_HOVERED         = "node_hovered"
    EDGE_CLICKED         = "edge_clicked"
    PHASE_CLICKED        = "phase_clicked"
    STEP_CLICKED         = "step_clicked"
    AGENT_CLICKED        = "agent_clicked"
    SCENE_READY          = "scene_ready"
    PLAYBACK_ENDED       = "playback_ended"
    USER_EDIT_FIELD      = "user_edit_field"
    VIEWPORT_CHANGED     = "viewport_changed"


# ═══════════════════════════════════════════════════
# NODE TYPES & VISUAL CONFIG
# ═══════════════════════════════════════════════════

class NodeVisualType(str, Enum):
    GOAL     = "goal"       # Hexagon, amber
    WORKFLOW = "workflow"   # Rounded rect, blue
    INSIGHT  = "insight"    # Diamond, purple
    DOCUMENT = "document"   # Folded corner rect, green
    AGENT    = "agent"      # Circle, white
    PHASE    = "phase"      # Wide pill, teal
    STEP     = "step"       # Small rect, grey


NODE_COLORS: Dict[str, str] = {
    "goal":     "#F5A623",   # amber
    "workflow": "#4A9EFF",   # blue
    "insight":  "#A855F7",   # purple
    "document": "#22C55E",   # green
    "agent":    "#E8E8EC",   # near-white
    "phase":    "#14B8A6",   # teal
    "step":     "#6B6B78",   # muted grey
    "error":    "#EF4444",   # red
    "active":   "#F5A623",   # amber highlight
}


# ═══════════════════════════════════════════════════
# COMMAND DATACLASSES
# ═══════════════════════════════════════════════════

@dataclass
class SimCommand:
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def clear_scene(cls) -> "SimCommand":
        return cls(type=CommandType.CLEAR_SCENE)

    @classmethod
    def render_node(
        cls,
        node_id: str,
        node_type: str,
        label: str,
        summary: str = "",
        position: Optional[Dict] = None,
        relevance: float = 1.0,
    ) -> "SimCommand":
        return cls(
            type=CommandType.RENDER_NODE,
            payload={
                "node_id":   node_id,
                "node_type": node_type,
                "label":     label[:60],
                "summary":   summary[:200],
                "color":     NODE_COLORS.get(node_type, "#6B6B78"),
                "position":  position or {"x": 0, "y": 0, "z": 0},
                "relevance": round(relevance, 3),
            },
        )

    @classmethod
    def render_edge(
        cls,
        from_id: str,
        to_id: str,
        edge_type: str,
        strength: float = 1.0,
        label: str = "",
    ) -> "SimCommand":
        return cls(
            type=CommandType.RENDER_EDGE,
            payload={
                "from_id":   from_id,
                "to_id":     to_id,
                "edge_type": edge_type,
                "strength":  round(strength, 3),
                "label":     label[:40],
            },
        )

    @classmethod
    def highlight_node(
        cls, node_id: str, color: str = "#F5A623", pulse: bool = True
    ) -> "SimCommand":
        return cls(
            type=CommandType.HIGHLIGHT_NODE,
            payload={"node_id": node_id, "color": color, "pulse": pulse},
        )

    @classmethod
    def render_workflow(cls, workflow_data: dict) -> "SimCommand":
        """workflow_data: output of ArchitectAgent.run()"""
        phases = []
        for i, phase in enumerate(workflow_data.get("phases", [])):
            phases.append({
                "phase_index": i,
                "phase_name":  phase.get("phase_name", f"Phase {i+1}"),
                "objective":   phase.get("objective", "")[:120],
                "status":      "pending",
                "steps": [
                    {
                        "step_index":    j,
                        "action":        s.get("action", "")[:80],
                        "difficulty":    s.get("difficulty_level", "Medium"),
                        "estimated_time": s.get("estimated_time", ""),
                        "outcome":       s.get("expected_outcome", "")[:80],
                        "tools":         s.get("suggested_tools", [])[:3],
                        "status":        "pending",
                    }
                    for j, s in enumerate(phase.get("steps", []))
                ],
            })
        return cls(
            type=CommandType.RENDER_WORKFLOW,
            payload={
                "goal_summary":    workflow_data.get("goal_summary", "")[:150],
                "phases":          phases,
                "top_risks":       workflow_data.get("top_risks", [])[:3],
                "first_72_hours":  workflow_data.get("first_72_hours", [])[:4],
            },
        )

    @classmethod
    def render_pipeline(cls, agents: List[str], tier: str) -> "SimCommand":
        return cls(
            type=CommandType.RENDER_PIPELINE,
            payload={"agents": agents, "tier": tier},
        )

    @classmethod
    def activate_agent(cls, agent_name: str) -> "SimCommand":
        return cls(
            type=CommandType.ACTIVATE_AGENT,
            payload={"agent_name": agent_name},
        )

    @classmethod
    def complete_agent(cls, agent_name: str, output_preview: str = "") -> "SimCommand":
        return cls(
            type=CommandType.COMPLETE_AGENT,
            payload={"agent_name": agent_name, "output_preview": output_preview[:120]},
        )

    @classmethod
    def load_data_object(cls, obj_id: str, data: dict, label: str) -> "SimCommand":
        """Spawn a manipulable data object in the scene."""
        return cls(
            type=CommandType.LOAD_DATA_OBJECT,
            payload={"obj_id": obj_id, "data": data, "label": label},
        )

    @classmethod
    def mutate_field(
        cls, obj_id: str, field_path: str, old_value: Any, new_value: Any
    ) -> "SimCommand":
        """Animate a field change on a loaded data object."""
        return cls(
            type=CommandType.MUTATE_FIELD,
            payload={
                "obj_id":     obj_id,
                "field_path": field_path,
                "old_value":  str(old_value)[:80],
                "new_value":  str(new_value)[:80],
            },
        )

    @classmethod
    def show_toast(cls, message: str, level: str = "info") -> "SimCommand":
        """level: info | success | warning | error"""
        return cls(
            type=CommandType.SHOW_TOAST,
            payload={"message": message[:120], "level": level},
        )

    @classmethod
    def update_status_bar(cls, text: str, progress: float = -1) -> "SimCommand":
        """progress: 0.0-1.0, or -1 for indeterminate."""
        return cls(
            type=CommandType.UPDATE_STATUS_BAR,
            payload={"text": text[:80], "progress": round(progress, 2)},
        )
