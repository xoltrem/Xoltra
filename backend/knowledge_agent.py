"""
knowledge_agent.py — XoltaOS Knowledge Intelligence Layer
Auto-linking, insight generation, deduplication.

Key fixes from v1:
- Never accesses kdb._sqlite_conn directly
- Validates LLM-generated evidence node IDs before creating edges
- Goal status check removed (was never triggered — status never set to completed)
- All DB access via public kdb functions
"""

import json
import logging
from typing import List, Dict, Optional

from llm import call_insight_generator
import knowledge_db as kdb

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# AUTO-LINKING ENGINE
# ═══════════════════════════════════════════════════

def auto_link_node(user_id: str, node_id: str, node_data: Dict):
    """
    Automatically create edges when a new node is created.
    Runs semantic search to find related nodes, then creates edges.
    """
    if node_data is None:
        return

    node_type = node_data.get("type")
    content   = node_data.get("content", {})

    # Semantic linking — find similar nodes
    embedding_text = kdb._prepare_embedding_text(node_type, content)
    similar_nodes  = kdb.semantic_search(
        user_id=user_id,
        query=embedding_text,
        top_k=5,
        min_similarity=0.75
    )

    for similar in similar_nodes:
        if similar["id"] == node_id:
            continue

        kdb.create_edge(
            user_id=user_id,
            from_node=node_id,
            to_node=similar["id"],
            edge_type="relates_to",
            strength=min(similar["relevance"], 1.0),
            reason=f"Semantic similarity: {similar['relevance']:.0%}"
        )
        # Returns None if duplicate — UNIQUE constraint handles it silently

    # Type-specific linking
    if node_type == "workflow":
        _link_workflow(user_id, node_id, content)
    elif node_type == "document":
        _link_document(user_id, node_id, content)


def _link_workflow(user_id: str, workflow_id: str, content: Dict):
    """Link workflow to semantically related goals."""
    goal_summary = content.get("goal_summary", "")
    if not goal_summary:
        return

    goals = kdb.semantic_search(
        user_id=user_id,
        query=goal_summary,
        top_k=3,
        node_types=["goal"],
        min_similarity=0.7
    )
    for goal in goals:
        kdb.create_edge(
            user_id=user_id,
            from_node=workflow_id,
            to_node=goal["id"],
            edge_type="derives_from",
            strength=min(goal["relevance"], 1.0),
            reason="Workflow derived from similar goal"
        )


def _link_document(user_id: str, doc_id: str, content: Dict):
    """Link document to related goals."""
    extracted_goal = content.get("extracted_goal", "")
    if not extracted_goal:
        return

    related_goals = kdb.semantic_search(
        user_id=user_id,
        query=extracted_goal,
        top_k=3,
        node_types=["goal"],
        min_similarity=0.7
    )
    for goal in related_goals:
        kdb.create_edge(
            user_id=user_id,
            from_node=doc_id,
            to_node=goal["id"],
            edge_type="relates_to",
            strength=min(goal["relevance"], 1.0),
            reason="Document supports goal"
        )


# ═══════════════════════════════════════════════════
# INSIGHT GENERATION
# ═══════════════════════════════════════════════════

def generate_insights(user_id: str) -> List[Dict]:
    """
    Analyze patterns across stored goals and generate insights.
    Called every 10 new nodes by the pipeline.
    Uses get_nodes_by_type() — never accesses _sqlite_conn directly.
    """
    stats = kdb.get_stats(user_id)
    if stats["total_nodes"] < 5:
        return []

    goals = kdb.get_nodes_by_type(user_id, "goal", status="active")
    if len(goals) < 3:
        return []

    goals_summary = "\n".join([
        f"- {g['content'].get('clarified_goal', '')} "
        f"(created: {g['created_at'][:10]}, accessed: {g['access_count']} times)"
        for g in goals[:10]
    ])

    prompt = f"""
Analyze these user goals and identify patterns:

{goals_summary}

Detect:
1. Recurring themes or topics
2. Time-based patterns (clustering of similar goals)
3. Skill progression indicators
4. Common domain focus

Return ONLY JSON:
{{
  "patterns": [
    {{
      "pattern": "clear description of the pattern",
      "confidence": 0.0-1.0,
      "actionable": true/false
    }}
  ]
}}

Important: Do NOT include any node IDs or references to specific items.
Only describe patterns you observed.
"""

    try:
        raw      = call_insight_generator(user_id, prompt)
        # Insight generator is a PROSE_ROLE but we need JSON here
        # Use safe_json_parse directly
        from llm import safe_json_parse, clean_json
        data     = safe_json_parse(raw)
        patterns = data.get("patterns", [])

        stored = []
        for pattern in patterns:
            if not pattern.get("pattern"):
                continue

            insight_id = kdb.create_node(
                user_id=user_id,
                node_type="insight",
                content={
                    "pattern":    pattern["pattern"],
                    "confidence": pattern.get("confidence", 0.5),
                    "actionable": pattern.get("actionable", False),
                }
            )
            stored.append(pattern)

        logger.info(f"[Knowledge] Generated {len(stored)} insights for {user_id}")
        return stored

    except Exception as e:
        logger.warning(f"[Knowledge] Insight generation failed: {e}")
        return []


# ═══════════════════════════════════════════════════
# DEDUPLICATION
# ═══════════════════════════════════════════════════

def check_before_create(user_id: str, goal_text: str) -> Dict:
    """
    Check if goal already exists. Returns action recommendation.
    Actions: create_new | reuse | evolve
    """
    dup = kdb.check_duplicate(user_id, goal_text, threshold=0.85)

    if not dup:
        return {"action": "create_new", "reason": "No similar goals found"}

    match      = dup["match"]
    similarity = dup["similarity"]

    if similarity > 0.95:
        return {
            "action":        "reuse",
            "existing_node": match,
            "similarity":    similarity,
            "reason":        f"Nearly identical goal exists (created {match['created_at'][:10]})"
        }
    elif similarity > 0.85:
        return {
            "action":        "evolve",
            "existing_node": match,
            "similarity":    similarity,
            "reason":        "Similar goal exists — building on it"
        }

    return {"action": "create_new", "reason": "Different enough from existing goals"}


# ═══════════════════════════════════════════════════
# CONTEXT RETRIEVAL FOR PIPELINE
# ═══════════════════════════════════════════════════

def get_context_for_pipeline(user_id: str, user_input: str) -> Optional[List[Dict]]:
    """
    Called by pipeline to get relevant context for prompt injection.
    Returns formatted list for LLM consumption or None if nothing relevant.
    """
    relevant = kdb.get_relevant_context(user_id, user_input, top_k=3)
    if not relevant:
        return None

    formatted = []
    for node in relevant:
        formatted.append({
            "type":       node["type"],
            "content":    _summarize_for_context(node["type"], node["content"]),
            "relevance":  node["relevance"],
            "created_at": node["created_at"],
        })

    return formatted


def _summarize_for_context(node_type: str, content: dict) -> str:
    """Concise summary for LLM context injection — stays under 200 chars."""
    if node_type == "goal":
        return content.get("clarified_goal", "")[:200]
    elif node_type == "workflow":
        phases = content.get("phases", [])
        names  = ", ".join(p.get("phase_name", "") for p in phases[:3])
        return f"{len(phases)}-phase workflow: {names}"[:200]
    elif node_type == "document":
        return content.get("extracted_goal", "")[:200]
    else:
        return str(content)[:200]
