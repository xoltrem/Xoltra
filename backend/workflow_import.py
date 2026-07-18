"""
workflow_import.py — Xoltra Workflow Import / Rebuild

Powers the onboarding "rebuild your existing automation" flow
(POST /api/workflows/import/parse). Takes a pasted n8n export, a Make.com
blueprint, a rough description of a Zapier zap, or just plain English
("when a new row hits my sheet, email me a summary") and turns it into an
ordered set of PROPOSED Xoltra nodes for the user to review — never saved
until they explicitly accept, same trust model as workflow_assistant.py's
one-node-at-a-time review, just for a whole imported flow at once.

Two responsibilities, kept separate on purpose:
  1. parse_import()      — LLM maps the source onto Xoltra's real node
                            catalogue. Only ever proposes types that
                            actually exist in node_library's registry.
  2. compile_steps_to_graph() — deterministic Python, NOT the LLM, turns
     accepted steps into an actually-runnable graph (nodes + edges) that
     matches how workflow_engine.py resolves inputs at runtime. LLMs are
     good at "what should this step do", unreliable at "which exact input
     port does node type X read from" — that part is code, not a prompt.
"""

import json
import logging
import uuid
from typing import Optional

import knowledge_db as kdb
import node_library
from llm import call_llm, safe_json_parse
from roles import get_role_preamble

logger = logging.getLogger(__name__)

_ASSISTANT_ROLE = "architect"

# Every node type Xoltra can actually run, and how to reach it — kept as a
# fallback the LLM must map onto, never invent a new one. Sourced live from
# node_library so this can never drift out of sync with the real registry.
def _catalogue_for_prompt() -> str:
    lines = []
    for defn in node_library.list_node_definitions():
        param_hint = _PARAM_HINTS.get(defn["node_type"], "")
        lines.append(f"- {defn['node_type']} ({defn['category']}): {defn['description']} {param_hint}")
    return "\n".join(lines)


# Params each executor actually reads (node_library.py's Port schema only
# covers wired inputs/outputs, not the static `params` dict) — written by
# hand from node_library.py's _exec_* functions, not guessed.
_PARAM_HINTS = {
    "trigger.schedule":            "params: {cron}",
    "integration.http_request":    "params: {method, url, headers, body}",
    "integration.send_email":      "params: {host, port, to, subject, body, from, username, password}",
    "ai.cohere_generate":          "reads a wired-in 'prompt' input, not a param — see ai_prompt_template below",
    "ai.web_search":               "params: {query, num_results} (query can also come from a wired input)",
    "logic.condition":             "params: {expression} — a Python-like boolean expression, e.g. \"status == 'active'\"",
    "utility.set_variable":        "params: {variable_name, variable_value}",
    "utility.transform":           "params: {template} — a Jinja2 template string",
    "utility.delay":               "params: {seconds}",
}

# Which input port an auto-chained edge should target on each node type,
# so a linear import produces edges workflow_engine.py can actually resolve
# (see workflow_engine.py's _build_node_inputs — unmapped ports just get
# dumped into a generic 'data' key, which most nodes ignore).
_PRIMARY_INPUT_PORT = {
    "ai.web_search":       "query",
    "logic.condition":     "value",
    "logic.loop":          "items",
    "utility.set_variable": "value",
}

_MAX_SOURCE_CHARS = 12000  # keep the prompt (and the LLM bill) bounded


def parse_import(user_id: str, raw_text: str, conversation_id: Optional[str] = None) -> dict:
    """
    Returns:
    {
      "source_detected": "n8n" | "make" | "zapier" | "freeform",
      "original_step_count": int,
      "steps": [
        {
          "step_index": int,
          "label": str,
          "node_type": str,           # one of node_library's real types
          "params": dict,
          "ai_prompt_template": str | None,
          "why": str,                 # one sentence, shown to the user live
          "source_step_label": str | None,
          "fidelity": "exact" | "approximate",
          "fidelity_note": str | None # e.g. "mapped to a generic HTTP call — no native Slack node yet"
        }, ...
      ],
      "warnings": [str, ...]
    }
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("source_text is required")

    raw_text = raw_text.strip()[:_MAX_SOURCE_CHARS]
    source_detected, source_summary, original_step_count = _detect_and_summarize(raw_text)

    preamble = get_role_preamble("default")

    prompt = f"""
You are rebuilding an existing automation as a Xoltra workflow. Xoltra can ONLY
run the node types listed below — you MUST map every step onto one of these
exact node_type strings. If nothing fits well, still pick the closest one and
say so honestly in fidelity_note rather than inventing a node type that doesn't
exist.

XOLTRA'S REAL NODE CATALOGUE:
{_catalogue_for_prompt()}

For any ai.cohere_generate step, put the actual prompt text in
"ai_prompt_template" (plain instructional text, may reference prior step
output conversationally, e.g. "Summarize the email above in two sentences.")
— do NOT put prompt text in params, that node type doesn't read params.

Detected source format: {source_detected}

SOURCE AUTOMATION ({original_step_count} step(s) detected):
{source_summary}

Rules:
1. Preserve the original order.
2. One Xoltra node per meaningful source step — don't merge or invent extra steps.
3. Every workflow needs a trigger first. If the source has a real trigger, map it
   to trigger.webhook or trigger.schedule as appropriate. If the source is a
   freeform description with no clear trigger, use trigger.manual for step 0.
4. "why" is ONE short sentence, written for a non-technical operator watching
   this build live — plain language, no jargon.
5. Set fidelity to "approximate" and explain in fidelity_note whenever the
   mapping loses something real (e.g. a named integration collapsed into a
   generic HTTP call, since Xoltra doesn't have a native connector for it yet).

Return ONLY JSON, no prose outside it:
{{"steps": [
  {{"step_index": 0, "label": "string", "node_type": "string", "params": {{}},
    "ai_prompt_template": "string or null", "why": "string",
    "source_step_label": "string or null",
    "fidelity": "exact" | "approximate", "fidelity_note": "string or null"}}
]}}
"""

    import llm as llm_module
    llm_module.set_usage_context(user_id=user_id, execution_id=conversation_id)

    try:
        raw = call_llm(_ASSISTANT_ROLE, prompt, role_preamble=preamble)
        data = safe_json_parse(raw)
    except Exception as e:
        logger.error(f"[WorkflowImport] parse failed for {user_id[:8]}: {e}")
        raise RuntimeError(f"Import parsing failed: {e}") from e

    steps, warnings = _validate_steps(data.get("steps"))

    if conversation_id:
        try:
            kdb.create_node(
                user_id=user_id,
                node_type="import_turn",
                content={"source_detected": source_detected, "step_count": len(steps)},
                conversation_id=conversation_id,
            )
        except Exception as e:
            logger.warning(f"[WorkflowImport] failed to store import_turn: {e}")

    return {
        "source_detected": source_detected,
        "original_step_count": original_step_count,
        "steps": steps,
        "warnings": warnings,
    }


def _detect_and_summarize(raw_text: str) -> tuple:
    """Returns (source_detected, compact_summary_for_prompt, step_count)."""
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError):
        return "freeform", raw_text, 1

    if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):
        # n8n export shape
        lines = []
        for i, n in enumerate(data["nodes"]):
            name = n.get("name", f"Step {i+1}")
            ntype = n.get("type", "unknown")
            params = n.get("parameters", {})
            param_str = ", ".join(f"{k}={str(v)[:60]}" for k, v in list(params.items())[:4])
            lines.append(f"{i+1}. \"{name}\" ({ntype}) — {param_str}")
        return "n8n", "\n".join(lines), len(data["nodes"])

    if isinstance(data, dict) and "flow" in data and isinstance(data["flow"], list):
        # Make.com blueprint shape
        lines = []
        for i, n in enumerate(data["flow"]):
            module = n.get("module", f"Step {i+1}")
            mapper = n.get("mapper", {})
            param_str = ", ".join(f"{k}={str(v)[:60]}" for k, v in list(mapper.items())[:4])
            lines.append(f"{i+1}. {module} — {param_str}")
        return "make", "\n".join(lines), len(data["flow"])

    if isinstance(data, dict) and "steps" in data and isinstance(data["steps"], list):
        # Loosely-structured Zapier-style step list
        lines = []
        for i, s in enumerate(data["steps"]):
            lines.append(f"{i+1}. {json.dumps(s)[:200]}")
        return "zapier", "\n".join(lines), len(data["steps"])

    # Valid JSON but not a shape we recognize — still hand it to the LLM raw.
    return "freeform", json.dumps(data)[:_MAX_SOURCE_CHARS], 1


def _validate_steps(steps) -> tuple:
    """Drop anything that doesn't map to a real, currently-registered node type."""
    valid_types = {d["node_type"] for d in node_library.list_node_definitions()}
    out, warnings = [], []

    if not isinstance(steps, list) or not steps:
        raise RuntimeError("The assistant didn't return any usable steps — try rephrasing or pasting the export again.")

    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            continue
        node_type = s.get("node_type")
        label = (s.get("label") or "").strip()
        if node_type not in valid_types:
            warnings.append(f"Step {i+1} (\"{label or node_type}\") skipped — no matching Xoltra node type.")
            continue
        if not label:
            continue
        out.append({
            "step_index": len(out),
            "label": label[:80],
            "node_type": node_type,
            "params": s.get("params") if isinstance(s.get("params"), dict) else {},
            "ai_prompt_template": (s.get("ai_prompt_template") or None),
            "why": (s.get("why") or "").strip()[:200] or "Rebuilt from your existing automation.",
            "source_step_label": s.get("source_step_label"),
            "fidelity": "approximate" if s.get("fidelity") == "approximate" else "exact",
            "fidelity_note": (s.get("fidelity_note") or None),
        })

    if not out:
        raise RuntimeError("None of the proposed steps matched a real Xoltra node — try describing it differently.")

    return out, warnings


def compile_steps_to_graph(accepted_steps: list) -> dict:
    """
    Deterministic: accepted steps (in order) -> {nodes, edges} matching
    workflow_engine.py's edge-resolution rules. Not LLM-driven — see the
    module docstring for why.
    """
    nodes, edges = [], []
    prev_id = None
    x = 0

    # Guarantee a trigger exists — imports missing one (freeform text with
    # no obvious trigger) still need to be runnable.
    if not accepted_steps or not accepted_steps[0]["node_type"].startswith("trigger."):
        trigger_id = str(uuid.uuid4())
        nodes.append({
            "id": trigger_id, "type": "trigger.manual", "label": "Start",
            "params": {}, "position": {"x": x, "y": 100},
        })
        prev_id = trigger_id
        x += 280

    for step in accepted_steps:
        node_id = str(uuid.uuid4())
        node_type = step["node_type"]
        params = dict(step.get("params") or {})

        # ai.cohere_generate needs a wired 'prompt' input, not a param —
        # synthesize a transform node that renders the static prompt text
        # as this node's input, rather than silently dropping it.
        if node_type == "ai.cohere_generate" and step.get("ai_prompt_template"):
            transform_id = str(uuid.uuid4())
            nodes.append({
                "id": transform_id, "type": "utility.transform",
                "label": f"{step['label']} — prompt",
                "params": {"template": step["ai_prompt_template"]},
                "position": {"x": x, "y": 100},
            })
            if prev_id:
                edges.append(_edge(prev_id, transform_id, target_port="data"))
            prev_id = transform_id
            x += 280

        nodes.append({
            "id": node_id, "type": node_type, "label": step["label"],
            "params": params, "position": {"x": x, "y": 100},
        })

        if prev_id:
            target_port = "prompt" if node_type == "ai.cohere_generate" else _PRIMARY_INPUT_PORT.get(node_type, "data")
            source_port = "result" if nodes[-2]["type"] == "utility.transform" and node_type == "ai.cohere_generate" else None
            edges.append(_edge(prev_id, node_id, source_port=source_port, target_port=target_port))

        prev_id = node_id
        x += 280

    return {"nodes": nodes, "edges": edges}


def _edge(source: str, target: str, source_port: Optional[str] = None, target_port: str = "data") -> dict:
    e = {"id": str(uuid.uuid4()), "source": source, "target": target, "target_port": target_port}
    if source_port:
        e["source_port"] = source_port
    return e
