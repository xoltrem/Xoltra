"""
workflow_assistant.py — Xoltra Workflow Chat Assistant
Powers the "Create Workflow" chat panel (AIAssistantPanel.tsx →
POST /api/workflows/assistant). Proposes exactly one node per turn;
never writes to a workflow itself — the frontend requires an explicit
"Add to Canvas" click before anything is added.
"""

import logging
from typing import Optional

import knowledge_db as kdb
from llm import call_llm, safe_json_parse
from roles import get_role_preamble

logger = logging.getLogger(__name__)

_ASSISTANT_ROLE = "architect"


def handle_assistant_message(
    user_id: str,
    message: str,
    role_id: str = "default",
    conversation_id: str = None,
) -> dict:
    if not message or not message.strip():
        raise ValueError("message is required")

    preamble = get_role_preamble(role_id)

    import llm as llm_module
    llm_module.set_usage_context(user_id=user_id, execution_id=conversation_id)

    prompt = f"""
You are the Xoltra Workflow Assistant in a chat panel next to a workflow canvas.

1. Reply conversationally, 1-3 sentences.
2. If the message describes ONE concrete automation step, propose that single node.
3. If vague or chit-chat, propose nothing and ask a clarifying question.
4. Never propose more than one node, even for multi-step requests — propose the
   first step and say you'll build the rest one at a time.
5. actions must be concrete: "VERB target", e.g. "POST api.slack.com/chat.postMessage".

category must be exactly one of: trigger, ai, integration, logic, utility

Return ONLY JSON:
{{"reply": "string", "proposed_node": {{"label": "string", "category": "string", "actions": ["string"]}} | null}}

User message: {message}
"""
    try:
        raw  = call_llm(_ASSISTANT_ROLE, prompt, role_preamble=preamble)
        data = safe_json_parse(raw)
    except Exception as e:
        logger.error(f"[WorkflowAssistant] failed for {user_id[:8]}: {e}")
        raise RuntimeError(f"Assistant failed to respond: {e}") from e

    reply = (data.get("reply") or "").strip() or "Could you rephrase that?"
    node  = _validate_node(data.get("proposed_node"))

    # Tag this turn to the conversation so "delete chat" in the UI can wipe
    # everything the AI learned from it via delete_conversation_memory().
    # Best-effort: a storage hiccup should never break the chat reply itself.
    if conversation_id:
        try:
            kdb.create_node(
                user_id=user_id,
                node_type="chat_turn",
                content={"message": message, "reply": reply, "proposed_node": node},
                conversation_id=conversation_id,
            )
        except Exception as e:
            logger.warning(f"[WorkflowAssistant] failed to store chat_turn: {e}")

    return {"reply": reply, "proposed_node": node}


def _validate_node(node) -> Optional[dict]:
    if not isinstance(node, dict):
        return None
    valid = {"trigger", "ai", "integration", "logic", "utility"}
    label = (node.get("label") or "").strip()
    cat   = (node.get("category") or "").strip().lower()
    acts  = node.get("actions")

    if not label or cat not in valid or not isinstance(acts, list) or not all(isinstance(a, str) for a in acts):
        return None
    return {"label": label[:80], "category": cat, "actions": acts[:5]}
