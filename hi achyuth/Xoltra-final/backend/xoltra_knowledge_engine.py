"""
xoltra_knowledge_engine.py — Xoltra Knowledge Integration Layer
Streamlit-facing logic for Features 4 & 5.

Three public entry points:
  A. compact_session()            — save a session to the knowledge graph
  B. build_aware_system_prompt()  — inject persona context into system prompt
  C. get_context_by_mode()        — fast (top_k=1) vs thinking (top_k=5 + edges)

Constraints honoured:
  - kdb.init_storage() never called here — caller (Streamlit app) owns that
  - All DB access via public kdb functions only — never kdb._local / kdb._conn
  - Injected context stays under 500 tokens (enforced by _trim_to_token_budget)
  - All LLM calls go through llm.call_llm() — no direct Cohere usage
"""

import logging
from datetime import datetime
from typing import Optional

import knowledge_db as kdb
import knowledge_agent
from llm import call_llm, safe_json_parse

logger = logging.getLogger(__name__)

# Rough token estimator — avoids adding tiktoken as a dependency.
# 1 token ≈ 4 characters for English prose. We use 3.5 chars/token
# (slightly conservative) so we stay under budget even with short words.
_CHARS_PER_TOKEN = 3.5
_MAX_CONTEXT_TOKENS = 500
_MAX_CONTEXT_CHARS = int(_MAX_CONTEXT_TOKENS * _CHARS_PER_TOKEN)  # 1750 chars


# ═══════════════════════════════════════════════════════════════════
# A. SESSION COMPACTION
# ═══════════════════════════════════════════════════════════════════

def compact_session(
    user_id: str,
    messages: list[dict],
    session_topic: Optional[str] = None,
) -> Optional[dict]:
    """
    Save a Streamlit session to the knowledge graph.

    Called when the user clicks "Save Session" or the session ends.
    Analyses the conversation, classifies it as a goal or insight,
    creates the appropriate node, then auto-links it into the graph.

    Args:
        messages:      st.session_state.messages — list of
                       {"role": "user"|"assistant", "content": str}
        session_topic: Optional UI-provided label for the session.

    Returns:
        {node_id, node_type, summary, linked} on success.
        None if session is too short to be worth storing.
    """
    # ── Guard: need at least 2 user turns to be worth storing ─────────────
    user_turns = [m for m in messages if m.get("role") == "user"]
    if len(user_turns) < 2:
        logger.info("[Compaction] Session too short — skipping")
        return None

    # ── Build transcript (cap at last 20 messages to stay LLM-friendly) ───
    recent   = messages[-20:]
    dialogue = "\n".join(
        f"{m['role'].upper()}: {str(m['content'])[:300]}"
        for m in recent
        if m.get("role") in ("user", "assistant") and m.get("content")
    )

    topic_hint = f"Session label provided by user: {session_topic}\n" if session_topic else ""

    prompt = f"""
Analyse this conversation and extract a structured summary for long-term memory storage.

{topic_hint}CONVERSATION:
{dialogue}

Determine:
1. Is this conversation primarily goal-oriented (user trying to accomplish something specific)
   or insight/exploratory (user learning, brainstorming, or seeking understanding)?
2. What is the core takeaway worth remembering?

Return ONLY valid JSON — no markdown, no explanation:
{{
  "node_type": "goal" or "insight",
  "title": "short title under 80 characters",
  "summary": "2-3 sentence plain-English summary of what was discussed and resolved",
  "key_topics": ["topic1", "topic2", "topic3"],
  "goal_text": "if node_type is goal: the specific goal the user was pursuing, else null",
  "pattern": "if node_type is insight: the reusable insight or learning, else null",
  "confidence": 0.0-1.0
}}
"""

    try:
        # Use "architect" — a JSON role — so call_llm auto-cleans JSON fences
        raw    = call_llm("architect", prompt)
        parsed = safe_json_parse(raw)
    except Exception as e:
        logger.warning(f"[Compaction] LLM classification failed: {e}")
        # Fallback: create a minimal insight node from the raw dialogue
        parsed = _fallback_classification(messages, session_topic)

    node_type = parsed.get("node_type", "insight")
    title     = parsed.get("title", "Untitled session")
    summary   = parsed.get("summary", "")
    topics    = parsed.get("key_topics", [])
    confidence = float(parsed.get("confidence", 0.5))

    # ── Build node content matching kdb's embedding schema ────────────────
    # _prepare_embedding_text() keys by node_type — we must match those keys
    # so ChromaDB builds a useful embedding for future retrieval.
    if node_type == "goal":
        content = {
            "original_input":  user_turns[0].get("content", "")[:500],
            "clarified_goal":  parsed.get("goal_text") or summary,
            "title":           title,
            "key_topics":      topics,
            "session_summary": summary,
            "confidence":      confidence,
        }
    else:
        # insight node
        content = {
            "pattern":    parsed.get("pattern") or summary,
            "title":      title,
            "key_topics": topics,
            "confidence": confidence,
            "actionable": confidence > 0.7,
        }

    metadata = {
        "source":        "streamlit_session",
        "message_count": len(messages),
        "compacted_at":  datetime.utcnow().isoformat(),
        "session_topic": session_topic or "",
    }

    # ── Store ──────────────────────────────────────────────────────────────
    try:
        node_id   = kdb.create_node(user_id, node_type=node_type, content=content, metadata=metadata)
        node_data = {"type": node_type, "content": content}
        knowledge_agent.auto_link_node(user_id, node_id, node_data)

        logger.info(f"[Compaction] Stored {node_type} node {node_id[:8]} — '{title}'")

        return {
            "node_id":   node_id,
            "node_type": node_type,
            "summary":   summary,
            "title":     title,
            "linked":    True,
        }

    except Exception as e:
        logger.error(f"[Compaction] Storage failed: {e}")
        return None


def _fallback_classification(messages: list[dict], topic: Optional[str]) -> dict:
    """
    Minimal fallback when LLM classification fails.
    Creates a basic insight node from available metadata.
    """
    user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
    first_msg = str(user_msgs[0])[:200] if user_msgs else "Unknown session"

    return {
        "node_type":  "insight",
        "title":      topic or first_msg[:80],
        "summary":    f"Session with {len(messages)} messages. First query: {first_msg[:150]}",
        "key_topics": [],
        "pattern":    first_msg[:200],
        "confidence": 0.3,
    }


# ═══════════════════════════════════════════════════════════════════
# B. PATTERN-AWARE RESPONSE ENGINE
# ═══════════════════════════════════════════════════════════════════

def build_aware_system_prompt(
    user_id: str,
    base_prompt: str,
    user_message: str,
    mode: str = "fast",
) -> str:
    """
    Build a system prompt enriched with user persona context from the knowledge graph.

    Called before every LLM response generation. Retrieves relevant context
    and insight nodes, formats a "User Persona Context" block, and prepends it
    to the base system prompt. Total injection stays under 500 tokens.

    Args:
        base_prompt:  Your existing system prompt string.
        user_message: The current user message (used as retrieval query).
        mode:         "fast" or "thinking" — controls retrieval depth.

    Returns:
        Modified system prompt string with persona context injected.
        Returns base_prompt unchanged if nothing relevant is found.
    """
    # ── 1. Retrieve context nodes ──────────────────────────────────────────
    context_nodes = get_context_by_mode(user_id, user_message, mode)

    # ── 2. Fetch insight nodes specifically ───────────────────────────────
    # Insights encode user patterns like "prefers technical depth" —
    # these are fetched directly, not via semantic search, because they
    # describe the user rather than a specific topic.
    insight_nodes = _get_insight_nodes(user_id, user_message)

    if not context_nodes and not insight_nodes:
        return base_prompt

    # ── 3. Build the injection block ──────────────────────────────────────
    sections: list[str] = []

    if insight_nodes:
        patterns = "\n".join(
            f"  • {n['content'].get('pattern', '')}"
            for n in insight_nodes
            if n["content"].get("pattern")
        )
        if patterns:
            sections.append(f"USER PATTERNS OBSERVED:\n{patterns}")

    if context_nodes:
        ctx_lines = []
        for node in context_nodes:
            node_type = node["type"]
            relevance = node.get("relevance", 0)
            summary   = _summarize_node_for_prompt(node_type, node["content"])
            if summary:
                ctx_lines.append(f"  [{node_type.upper()} | {relevance:.0%}] {summary}")

        if ctx_lines:
            sections.append("RELEVANT PRIOR CONTEXT:\n" + "\n".join(ctx_lines))

    if not sections:
        return base_prompt

    # ── 4. Enforce token budget ────────────────────────────────────────────
    raw_block = (
        "--- USER PERSONA CONTEXT ---\n"
        "The following is derived from the user's history. "
        "Adapt your response style and depth accordingly.\n\n"
        + "\n\n".join(sections)
        + "\n--- END PERSONA CONTEXT ---\n\n"
    )
    trimmed_block = _trim_to_token_budget(raw_block, _MAX_CONTEXT_CHARS)

    return trimmed_block + base_prompt


def _get_insight_nodes(user_id: str, user_message: str, max_insights: int = 3) -> list[dict]:
    """
    Retrieve the most relevant insight nodes for persona injection.
    Uses semantic search scoped to type=insight, then falls back to
    most recent insights if semantic search returns nothing.
    """
    try:
        # First: semantic search for topic-relevant insights
        semantic_insights = kdb.semantic_search(
            user_id,
            query=user_message,
            top_k=max_insights,
            node_types=["insight"],
            min_similarity=0.6,   # Lower threshold — insights are generalised patterns
        )
        if semantic_insights:
            return semantic_insights[:max_insights]

        # Fallback: most recent insights regardless of topic relevance
        all_insights = kdb.get_nodes_by_type(user_id, "insight", status="active")
        # Sort by created_at descending
        all_insights.sort(key=lambda n: n.get("created_at", ""), reverse=True)
        return all_insights[:max_insights]

    except Exception as e:
        logger.warning(f"[PersonaContext] Insight retrieval failed: {e}")
        return []


def _summarize_node_for_prompt(node_type: str, content: dict) -> str:
    """
    Concise single-line summary for system prompt injection.
    Kept short — these summaries are aggregated into a 500-token budget.
    """
    if node_type == "goal":
        return (content.get("clarified_goal") or content.get("title", ""))[:180]
    elif node_type == "workflow":
        phases = content.get("phases", [])
        names  = ", ".join(p.get("phase_name", "") for p in phases[:3])
        return f"{len(phases)}-phase plan: {names}"[:180]
    elif node_type == "document":
        return content.get("extracted_goal", "")[:180]
    elif node_type == "insight":
        return content.get("pattern", "")[:180]
    else:
        import json as _json
        return _json.dumps(content)[:180]


def _trim_to_token_budget(text: str, max_chars: int) -> str:
    """
    Trim a text block to fit within the character budget.
    Cuts at the last newline within budget to avoid mid-sentence truncation.
    """
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_newline = truncated.rfind("\n")
    if last_newline > max_chars * 0.7:      # only cut at newline if not too far back
        truncated = truncated[:last_newline]

    return truncated + "\n[Context trimmed to fit token budget]\n"


# ═══════════════════════════════════════════════════════════════════
# C. FAST VS. THINKING CONTEXT RETRIEVAL
# ═══════════════════════════════════════════════════════════════════

def get_context_by_mode(
    user_id: str,
    user_input: str,
    mode: str = "fast",
) -> list[dict]:
    """
    Retrieve knowledge graph context scaled to the UI mode.

    Fast mode:
      - top_k=1 from kdb.get_relevant_context()
      - Single most relevant node only
      - Minimal latency — appropriate for quick replies

    Thinking mode:
      - top_k=5 from kdb.get_relevant_context()
      - For each node: fetch up to 2 outgoing edges + their neighbour summaries
      - Inject active insight nodes
      - Full multi-layered context for the agentic reasoning loop

    Args:
        user_input: The current user message, used as semantic search query.
        mode:       "fast" | "thinking"

    Returns:
        List of enriched node dicts, each with a "relevance" score.
        Empty list if nothing relevant found or KB not yet populated.
    """
    if mode == "thinking":
        return _get_thinking_context(user_id, user_input)
    return _get_fast_context(user_id, user_input)


def _get_fast_context(user_id: str, user_input: str) -> list[dict]:
    """
    Fast mode: single best match, no edge traversal.
    Target latency overhead: < 100ms.
    """
    try:
        results = kdb.get_relevant_context(user_id, user_input, top_k=1)
        return results
    except Exception as e:
        logger.warning(f"[Context/Fast] Retrieval failed: {e}")
        return []


def _get_thinking_context(user_id: str, user_input: str) -> list[dict]:
    """
    Thinking mode: top 5 nodes + edge traversal + active insights.

    Structure of returned list:
      - Primary nodes    (type=any, top semantic matches)
      - Neighbour nodes  (1 hop via outgoing edges from primary nodes)
      - Insight nodes    (type=insight, all active — independent of query)

    Deduplication: nodes already seen by ID are skipped.
    """
    seen_ids: set[str] = set()
    enriched: list[dict] = []

    # ── 1. Primary nodes — top 5 semantic matches ──────────────────────────
    try:
        primary = kdb.get_relevant_context(user_id, user_input, top_k=5)
    except Exception as e:
        logger.warning(f"[Context/Thinking] Primary retrieval failed: {e}")
        primary = []

    for node in primary:
        nid = node["id"]
        if nid not in seen_ids:
            node["context_layer"] = "primary"
            enriched.append(node)
            seen_ids.add(nid)

    # ── 2. Edge traversal — 1 hop from each primary node ──────────────────
    # Limit: 2 outgoing edges per primary node to control context size.
    for node in primary:
        try:
            edges = kdb.get_node_edges(user_id, node["id"], direction="outgoing")[:2]
        except Exception:
            continue

        for edge in edges:
            neighbour_id = edge.get("to_node")
            if not neighbour_id or neighbour_id in seen_ids:
                continue

            try:
                neighbour = kdb.get_node(user_id, neighbour_id, update_access=False)
            except Exception:
                continue

            if neighbour:
                # Neighbours inherit the edge strength as their relevance signal,
                # capped at 1.0 per the codebase contract
                neighbour["relevance"]     = min(edge.get("strength", 0.5), 1.0)
                neighbour["context_layer"] = "neighbour"
                neighbour["edge_reason"]   = edge.get("reason", "")
                enriched.append(neighbour)
                seen_ids.add(neighbour_id)

    # ── 3. Active insight nodes — injected independently of topic ──────────
    # Insights describe user behaviour patterns; they're always relevant in
    # thinking mode regardless of semantic proximity to the current query.
    try:
        insights = kdb.get_nodes_by_type(user_id, "insight", status="active")
        for insight in insights[:3]:          # cap at 3 to respect token budget
            iid = insight["id"]
            if iid not in seen_ids:
                insight["relevance"]     = insight["content"].get("confidence", 0.5)
                insight["context_layer"] = "insight"
                enriched.append(insight)
                seen_ids.add(iid)
    except Exception as e:
        logger.warning(f"[Context/Thinking] Insight injection failed: {e}")

    return enriched


# ═══════════════════════════════════════════════════════════════════
# STREAMLIT INIT HELPER
# ═══════════════════════════════════════════════════════════════════

def ensure_knowledge_base_ready() -> bool:
    """
    Call this once in your Streamlit app's main block:

        if "kb_ready" not in st.session_state:
            st.session_state.kb_ready = xke.ensure_knowledge_base_ready()

    Returns True if KB is ready, False if init failed.
    The guard on st.session_state ensures init_storage() is called exactly
    once per session — never on module import, never on every rerun.
    """
    try:
        kdb.init_storage()
        logger.info("[KnowledgeEngine] Storage ready")
        return True
    except Exception as e:
        logger.error(f"[KnowledgeEngine] init_storage() failed: {e}")
        return False
