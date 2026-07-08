"""
node_library.py — Xoltra Built-in Node Catalogue

Registry of all node types available in the workflow editor. Each node declares
its type, category, label, description, typed input/output ports, and an
execute() function that does the actual work at runtime.

Categories:
    trigger     — entry points that start a workflow run
    ai          — nodes that call LLMs (Cohere via llm.py)
    logic       — conditional routing, loops, merges
    integration — external HTTP calls, email (via Permission Bridge)
    utility     — variable management, transforms, delays

All nodes that touch external systems declare a NodeManifest and go through
the Permission Bridge's check_manifest() before executing. This is enforced
in the execute() function itself — the engine does not need to know which
nodes are external.

Usage:
    from node_library import get_node, list_node_definitions
    defn = get_node("ai.cohere_generate")
    result = defn.execute(inputs={"prompt": "hello"}, params={})
"""

import json
import time
import smtplib
import logging
import sys
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Callable

from Node.permission_bridge import create_permission_bridge, NodeManifest, NodeAction


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# NODE DEFINITION SCHEMA
# ═══════════════════════════════════════════════════

@dataclass
class Port:
    """A typed input or output port on a node."""
    name: str
    type: str           # "string" | "number" | "boolean" | "object" | "array" | "any"
    description: str = ""
    required: bool = True
    default: Any = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NodeDefinition:
    """
    Complete definition of a workflow node type.
    The execute function is not serialized — it's only used at runtime.
    """
    node_type: str
    category: str       # "trigger" | "ai" | "logic" | "integration" | "utility"
    label: str
    description: str
    inputs: List[Port]
    outputs: List[Port]
    execute_fn: Callable[[Dict, Dict], Dict] = field(repr=False, default=None)

    def execute(self, inputs: dict, params: dict) -> dict:
        """Run this node. Delegates to the registered execute_fn."""
        if self.execute_fn is None:
            raise NotImplementedError(f"Node '{self.node_type}' has no execute function")
        return self.execute_fn(inputs, params)

    def to_dict(self) -> dict:
        """Serializable representation for the GET /api/nodes endpoint."""
        return {
            "node_type":   self.node_type,
            "category":    self.category,
            "label":       self.label,
            "description": self.description,
            "inputs":      [p.to_dict() for p in self.inputs],
            "outputs":     [p.to_dict() for p in self.outputs],
        }


# ═══════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════

_registry: Dict[str, NodeDefinition] = {}


def register(defn: NodeDefinition):
    """Register a node definition in the catalogue."""
    _registry[defn.node_type] = defn


def get_node(node_type: str) -> NodeDefinition:
    """Retrieve a node definition by type. Raises KeyError if not found."""
    if node_type not in _registry:
        raise KeyError(f"Unknown node type: '{node_type}'. Available: {list(_registry.keys())}")
    return _registry[node_type]


def list_node_definitions() -> List[Dict]:
    """Return all registered node definitions as serializable dicts."""
    return [defn.to_dict() for defn in _registry.values()]


# ═══════════════════════════════════════════════════
# PERMISSION BRIDGE HELPER
# ═══════════════════════════════════════════════════

# Lazily initialized — the bridge is created once on first use
_bridge = None
_primitives = None


def _get_bridge():
    """Lazy-init the Permission Bridge singleton."""
    global _bridge, _primitives
    if _bridge is None:
        _bridge, _primitives = create_permission_bridge()
    return _bridge, _primitives


def _check_permission(node_type: str, action_type: str, target: str, scope: str):
    """
    Check a single action through the Permission Bridge.
    Raises PermissionError if denied.
    """
    bridge, _ = _get_bridge()

    manifest = NodeManifest(
        node_id=node_type,
        node_name=node_type,
        generated_by="user",
        permissions=[action_type],
        actions=[NodeAction(action_type=action_type, target=target, scope=scope)],

        safe_primitives_only=True,
    )
    result = bridge.check_manifest(manifest)
    if not result.allowed:
        raise PermissionError(
            f"Permission denied for {node_type}: {result.reason}. "
            f"Blocked: {result.blocked_actions}"
        )


# ═══════════════════════════════════════════════════
# TRIGGER NODES
# ═══════════════════════════════════════════════════

def _exec_trigger_schedule(inputs: dict, params: dict) -> dict:
    """
    Schedule trigger — fires on a cron expression.
    At runtime this is a no-op that passes through trigger_data;
    the actual scheduling is handled by the engine's scheduler.
    """
    return {
        "triggered": True,
        "trigger_type": "schedule",
        "cron": params.get("cron", ""),
        "data": inputs.get("trigger_data", {}),
    }


def _exec_trigger_webhook(inputs: dict, params: dict) -> dict:
    """
    Webhook trigger — receives HTTP POST data.
    The webhook body is passed in as trigger_data by the engine.
    """
    return {
        "triggered": True,
        "trigger_type": "webhook",
        "method": "POST",
        "data": inputs.get("trigger_data", {}),
        "headers": inputs.get("headers", {}),
    }


def _exec_trigger_manual(inputs: dict, params: dict) -> dict:
    """Manual trigger — run-now button. Passes through any provided data."""
    return {
        "triggered": True,
        "trigger_type": "manual",
        "data": inputs.get("trigger_data", {}),
    }


# ═══════════════════════════════════════════════════
# AI NODES
# ═══════════════════════════════════════════════════

def _exec_ai_cohere_generate(inputs: dict, params: dict) -> dict:
    """
    Generate text via Cohere using the existing llm.py call_llm function.
    Uses the 'architect' role by default — configurable via params.role.
    """
    from llm import call_llm

    prompt = inputs.get("prompt", "")
    if not prompt:
        raise ValueError("ai.cohere_generate requires a non-empty 'prompt' input")

    role        = params.get("role", "architect")
    preamble    = params.get("preamble", None)
    max_retries = int(params.get("retries", 2))

    result_text = call_llm(role, prompt, retries=max_retries, role_preamble=preamble)

    return {
        "text": result_text,
        "role": role,
        "prompt_length": len(prompt),
    }


def _exec_ai_cohere_embed(inputs: dict, params: dict) -> dict:
    """
    Generate an embedding vector via Cohere using llm.py generate_embedding.
    """
    from llm import generate_embedding

    text = inputs.get("text", "")
    if not text:
        raise ValueError("ai.cohere_embed requires a non-empty 'text' input")

    embedding = generate_embedding(text)
    if not embedding:
        raise RuntimeError("Embedding generation returned empty result")

    return {
        "embedding": embedding,
        "dimensions": len(embedding),
        "text_length": len(text),
    }


# ═══════════════════════════════════════════════════
# LOGIC NODES
# ═══════════════════════════════════════════════════

import ast
import operator as _op

# Whitelisted AST node types + operators for _safe_eval_condition().
# Anything not in these sets is rejected before Python's real eval/compile
# ever sees it — this is what actually closes the well-known restricted-eval
# escape (e.g. ().__class__.__bases__[0].__subclasses__()), since that trick
# requires Attribute + Call nodes, and neither is in the allowed set below.
_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.Name, ast.Load, ast.Constant, ast.List, ast.Tuple,
    ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.USub, ast.UAdd,
)

_BIN_OPS = {
    ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul,
    ast.Div: _op.truediv, ast.Mod: _op.mod,
}
_CMP_OPS = {
    ast.Eq: _op.eq, ast.NotEq: _op.ne, ast.Lt: _op.lt, ast.LtE: _op.le,
    ast.Gt: _op.gt, ast.GtE: _op.ge, ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def _safe_eval_condition(expression: str, variables: dict):
    """
    Evaluate a boolean-ish expression without ever calling Python's real
    Never runs Python's own general-purpose code evaluator on arbitrary
    syntax. Parses to an AST first and walks it,
    rejecting any node type not explicitly whitelisted (no Attribute,
    no Call, no Subscript, no Import, no Lambda) — so there is no
    attribute-chain escape path available, unlike restricted-builtins evaluation.
    """
    tree = ast.parse(expression, mode="eval")

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(
                f"Disallowed expression syntax: {type(node).__name__}. "
                f"Only comparisons, boolean logic, and basic arithmetic are permitted."
            )

    def _resolve_node(node):
        if isinstance(node, ast.Expression):
            return _resolve_node(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"Unknown variable in expression: '{node.id}'")
            return variables[node.id]
        if isinstance(node, ast.List):
            return [_resolve_node(e) for e in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(_resolve_node(e) for e in node.elts)
        if isinstance(node, ast.UnaryOp):
            val = _resolve_node(node.operand)
            return not val if isinstance(node.op, ast.Not) else (
                -val if isinstance(node.op, ast.USub) else +val
            )
        if isinstance(node, ast.BinOp):
            op_fn = _BIN_OPS.get(type(node.op))
            if op_fn is None:
                raise ValueError(f"Disallowed operator: {type(node.op).__name__}")
            return op_fn(_resolve_node(node.left), _resolve_node(node.right))
        if isinstance(node, ast.BoolOp):
            values = [_resolve_node(v) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = _resolve_node(node.left)
            for op_node, comparator in zip(node.ops, node.comparators):
                op_fn = _CMP_OPS.get(type(op_node))
                if op_fn is None:
                    raise ValueError(f"Disallowed comparison: {type(op_node).__name__}")
                right = _resolve_node(comparator)
                if not op_fn(left, right):
                    return False
                left = right
            return True
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    return _resolve_node(tree)


def _exec_logic_condition(inputs: dict, params: dict) -> dict:
    """
    Evaluate a boolean expression and route to true/false output.

    FIX: previously called Python's general-purpose code evaluator with
    __builtins__ stripped, which is a known-incomplete sandbox (attribute-chain
    escapes still reach dangerous classes without any builtins). Now uses
    _safe_eval_condition(), an AST-whitelist evaluator that never runs
    arbitrary syntax through the real evaluator at all — disallowed node
    types are rejected up front.

    params.expression: e.g. "value > 10", "status == 'active'"
    """
    expression = params.get("expression", "")
    if not expression:
        raise ValueError("logic.condition requires a non-empty 'expression' param")

    try:
        result = _safe_eval_condition(expression, dict(inputs))
        result = bool(result)
    except Exception as e:
        raise ValueError(f"Condition expression failed: {e}. Expression: '{expression}'") from e

    return {
        "result": result,
        "branch": "true" if result else "false",
        "expression": expression,
    }


def _exec_logic_loop(inputs: dict, params: dict) -> dict:
    """
    Iterate over a list input. Returns each item with its index.
    The engine should call the downstream nodes once per iteration.
    For v1, we collect all items and return them as a batch.
    """
    items = inputs.get("items", [])
    if not isinstance(items, list):
        raise ValueError("logic.loop requires 'items' input to be a list")

    results = []
    for i, item in enumerate(items):
        results.append({"index": i, "item": item})

    return {
        "iterations": results,
        "count": len(results),
    }


def _exec_logic_merge(inputs: dict, params: dict) -> dict:
    """
    Merge multiple upstream inputs into a single object.
    All inputs are collected into the output as-is.
    """
    strategy = params.get("strategy", "combine")

    if strategy == "combine":
        merged = {}
        for key, value in inputs.items():
            merged[key] = value
        return {"merged": merged}
    elif strategy == "array":
        return {"merged": list(inputs.values())}
    else:
        raise ValueError(f"Unknown merge strategy: '{strategy}'. Use 'combine' or 'array'")


# ═══════════════════════════════════════════════════
# INTEGRATION NODES
# ═══════════════════════════════════════════════════

def _exec_integration_http_request(inputs: dict, params: dict) -> dict:
    """
    Make an authenticated HTTP call via the Permission Bridge's safe_api_call.
    Goes through full permission checking before the request is made.
    """
    url    = params.get("url", "") or inputs.get("url", "")
    method = (params.get("method", "GET") or "GET").upper()

    if not url:
        raise ValueError("integration.http_request requires a 'url' param or input")

    headers = params.get("headers", {}) or inputs.get("headers", {})
    body    = params.get("body", None) or inputs.get("body", None)

    # Permission check via bridge
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    _check_permission("integration.http_request", method, domain, url)

    # Execute via safe primitives
    _, primitives = _get_bridge()
    response = primitives.safe_api_call(method=method, url=url, headers=headers, body=body)

    return {
        "status_code": 200,
        "response": response,
        "url": url,
        "method": method,
    }


def _exec_integration_send_email(inputs: dict, params: dict) -> dict:
    """
    Send an email via SMTP. Requires host, port, to, subject, body in params.
    Goes through Permission Bridge before sending.
    """
    host    = params.get("host", "")
    port    = int(params.get("port", 587))
    to_addr = params.get("to", "") or inputs.get("to", "")
    subject = params.get("subject", "") or inputs.get("subject", "")
    body    = params.get("body", "") or inputs.get("body", "")
    from_addr = params.get("from", "noreply@xoltra.local")
    username  = params.get("username", "")
    password  = params.get("password", "")

    if not host:
        raise ValueError("integration.send_email requires 'host' param")
    if not to_addr:
        raise ValueError("integration.send_email requires 'to' param or input")
    if not subject:
        raise ValueError("integration.send_email requires 'subject' param or input")

    # Permission check
    _check_permission("integration.send_email", "POST", host, f"smtp://{host}:{port}")

    msg = MIMEMultipart()
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            if port == 587:
                server.starttls()
                server.ehlo()
            if username and password:
                server.login(username, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
    except Exception as e:
        raise RuntimeError(f"Email send failed: {e}") from e

    return {
        "sent": True,
        "to": to_addr,
        "subject": subject,
    }


# ═══════════════════════════════════════════════════
# UTILITY NODES
# ═══════════════════════════════════════════════════

def _exec_utility_set_variable(inputs: dict, params: dict) -> dict:
    """
    Set a named variable in the run context.
    The engine reads 'variable_name' and 'variable_value' from the output
    and writes them into RunContext.variables.
    """
    var_name  = params.get("variable_name", "")
    var_value = params.get("variable_value") if "variable_value" in params else inputs.get("value")

    if not var_name:
        raise ValueError("utility.set_variable requires a 'variable_name' param")

    return {
        "variable_name": var_name,
        "variable_value": var_value,
        "_set_variable": True,  # Signal to engine to write to context
    }


def _exec_utility_transform(inputs: dict, params: dict) -> dict:
    """
    Apply a Jinja2 template to the input data.
    The template has access to all inputs as template variables.
    """
    from jinja2 import Environment, BaseLoader, StrictUndefined

    template_str = params.get("template", "")
    if not template_str:
        raise ValueError("utility.transform requires a 'template' param")

    env = Environment(
        loader=BaseLoader(),
        undefined=StrictUndefined,
        autoescape=False,
    )

    try:
        template = env.from_string(template_str)
        rendered = template.render(**inputs)
    except Exception as e:
        raise ValueError(f"Jinja2 template rendering failed: {e}") from e

    # Try to parse as JSON — if it fails, return as string
    try:
        parsed = json.loads(rendered)
        return {"result": parsed}
    except (json.JSONDecodeError, TypeError):
        return {"result": rendered}


def _exec_utility_delay(inputs: dict, params: dict) -> dict:
    """Wait N seconds. Used for rate limiting or sequencing."""
    seconds = float(params.get("seconds", 1))
    if seconds < 0:
        raise ValueError("Delay seconds must be >= 0")
    if seconds > 300:
        raise ValueError("Delay cannot exceed 300 seconds (5 minutes)")

    time.sleep(seconds)

    return {
        "delayed": True,
        "seconds": seconds,
        "data": inputs.get("data"),  # Pass through the input data
    }


# ═══════════════════════════════════════════════════
# REGISTER ALL BUILT-IN NODES
# ═══════════════════════════════════════════════════

def _register_builtins():
    """Register all v1 built-in nodes. Called once at module load."""

    # ── Triggers ──
    register(NodeDefinition(
        node_type="trigger.schedule",
        category="trigger",
        label="Schedule Trigger",
        description="Fires on a cron schedule. Configure the cron expression in params.",
        inputs=[Port("trigger_data", "object", "Data passed at trigger time", required=False)],
        outputs=[Port("data", "object", "Trigger payload"), Port("trigger_type", "string", "Always 'schedule'")],
        execute_fn=_exec_trigger_schedule,
    ))

    register(NodeDefinition(
        node_type="trigger.webhook",
        category="trigger",
        label="Webhook Trigger",
        description="Receives an HTTP POST. The request body becomes the output.",
        inputs=[
            Port("trigger_data", "object", "HTTP request body", required=False),
            Port("headers", "object", "HTTP request headers", required=False),
        ],
        outputs=[Port("data", "object", "Webhook payload"), Port("trigger_type", "string", "Always 'webhook'")],
        execute_fn=_exec_trigger_webhook,
    ))

    register(NodeDefinition(
        node_type="trigger.manual",
        category="trigger",
        label="Manual Trigger",
        description="Run-now button. Passes through any provided data.",
        inputs=[Port("trigger_data", "object", "Optional data to pass through", required=False)],
        outputs=[Port("data", "object", "Trigger payload"), Port("trigger_type", "string", "Always 'manual'")],
        execute_fn=_exec_trigger_manual,
    ))

    # ── AI ──
    register(NodeDefinition(
        node_type="ai.cohere_generate",
        category="ai",
        label="Cohere Generate",
        description="Generate text via Cohere LLM using the existing llm.py call_llm.",
        inputs=[Port("prompt", "string", "The prompt to send to the LLM")],
        outputs=[
            Port("text", "string", "Generated text"),
            Port("role", "string", "LLM role used"),
        ],
        execute_fn=_exec_ai_cohere_generate,
    ))

    register(NodeDefinition(
        node_type="ai.cohere_embed",
        category="ai",
        label="Cohere Embed",
        description="Generate an embedding vector for text via Cohere.",
        inputs=[Port("text", "string", "Text to embed")],
        outputs=[
            Port("embedding", "array", "Embedding vector"),
            Port("dimensions", "number", "Vector dimensionality"),
        ],
        execute_fn=_exec_ai_cohere_embed,
    ))

    # ── Logic ──
    register(NodeDefinition(
        node_type="logic.condition",
        category="logic",
        label="Condition",
        description="Evaluate a boolean expression. Routes to 'true' or 'false' branch.",
        inputs=[Port("value", "any", "Value to evaluate", required=False)],
        outputs=[
            Port("result", "boolean", "Evaluation result"),
            Port("branch", "string", "'true' or 'false'"),
        ],
        execute_fn=_exec_logic_condition,
    ))

    register(NodeDefinition(
        node_type="logic.loop",
        category="logic",
        label="Loop",
        description="Iterate over a list. Outputs each item with its index.",
        inputs=[Port("items", "array", "List to iterate over")],
        outputs=[
            Port("iterations", "array", "Array of {index, item} objects"),
            Port("count", "number", "Number of iterations"),
        ],
        execute_fn=_exec_logic_loop,
    ))

    register(NodeDefinition(
        node_type="logic.merge",
        category="logic",
        label="Merge",
        description="Wait for multiple inputs and merge them into a single output.",
        inputs=[
            Port("input_1", "any", "First input", required=False),
            Port("input_2", "any", "Second input", required=False),
            Port("input_3", "any", "Third input", required=False),
        ],
        outputs=[Port("merged", "object", "Merged output")],
        execute_fn=_exec_logic_merge,
    ))

    # ── Integration ──
    register(NodeDefinition(
        node_type="integration.http_request",
        category="integration",
        label="HTTP Request",
        description="Make an authenticated HTTP call via the Permission Bridge.",
        inputs=[
            Port("url", "string", "Request URL", required=False),
            Port("headers", "object", "Request headers", required=False),
            Port("body", "object", "Request body", required=False),
        ],
        outputs=[
            Port("status_code", "number", "HTTP status code"),
            Port("response", "object", "Response body"),
        ],
        execute_fn=_exec_integration_http_request,
    ))

    register(NodeDefinition(
        node_type="integration.send_email",
        category="integration",
        label="Send Email",
        description="Send an email via SMTP. Requires SMTP host/port in params.",
        inputs=[
            Port("to", "string", "Recipient email", required=False),
            Port("subject", "string", "Email subject", required=False),
            Port("body", "string", "Email body text", required=False),
        ],
        outputs=[
            Port("sent", "boolean", "Whether the email was sent"),
            Port("to", "string", "Recipient address"),
        ],
        execute_fn=_exec_integration_send_email,
    ))

    # ── Utility ──
    register(NodeDefinition(
        node_type="utility.set_variable",
        category="utility",
        label="Set Variable",
        description="Set a named variable in the workflow run context.",
        inputs=[Port("value", "any", "Value to store", required=False)],
        outputs=[
            Port("variable_name", "string", "Name of the variable"),
            Port("variable_value", "any", "Stored value"),
        ],
        execute_fn=_exec_utility_set_variable,
    ))

    register(NodeDefinition(
        node_type="utility.transform",
        category="utility",
        label="Transform",
        description="Apply a Jinja2 template to input data. Template has access to all inputs.",
        inputs=[Port("data", "any", "Input data for the template", required=False)],
        outputs=[Port("result", "any", "Transformed output")],
        execute_fn=_exec_utility_transform,
    ))

    register(NodeDefinition(
        node_type="utility.delay",
        category="utility",
        label="Delay",
        description="Wait N seconds before passing data to the next node.",
        inputs=[Port("data", "any", "Data to pass through", required=False)],
        outputs=[
            Port("delayed", "boolean", "Always true"),
            Port("seconds", "number", "Seconds waited"),
            Port("data", "any", "Passed-through input data"),
        ],
        execute_fn=_exec_utility_delay,
    ))


# Auto-register on import
_register_builtins()
