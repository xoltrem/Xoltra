"""
workflow_engine.py — Xoltra Workflow Execution Engine

The orchestrator that takes a saved workflow graph, topologically sorts
the nodes, executes each one in dependency order, passes outputs to
downstream nodes via edge mappings, and returns a complete run result.

Architecture:
    1. Load workflow from workflow_store
    2. Build a DAG from graph.edges
    3. Topological sort (Kahn's algorithm) — nodes run only after all
       upstream dependencies have completed
    4. Execute each node via node_library.get_node(type).execute()
    5. Map outputs to downstream inputs via edge port mappings
    6. Track per-node results in RunContext (status, timing, I/O, errors)
    7. On failure: mark the node as failed, skip all transitive dependents,
       continue any independent branches
    8. Emit SimCommands to unity_bridge at each step so Unity can
       visualize the run in real time

Run history is persisted to SQLite alongside workflow definitions.

Public API:
    run_workflow(workflow_id, trigger_data)  → full run result dict
    get_run(run_id)                          → single run result
    list_runs(workflow_id)                   → run history for a workflow
"""

import json
import uuid
import time
import logging
from datetime import datetime
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set

import knowledge_db as kdb
import workflow_store
import node_library
import unity_bridge
from simulation_types import SimCommand, CommandType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# RUN CONTEXT
# ═══════════════════════════════════════════════════

class RunContext:
    """
    Tracks the state of a single workflow execution.

    Attributes:
        run_id          — unique identifier for this run
        workflow_id     — which workflow is being executed
        started_at      — ISO-8601 timestamp
        finished_at     — ISO-8601 timestamp (set when run completes)
        status          — "running" | "success" | "failed" | "partial"
        node_results    — dict of node_id → per-node result
        variables       — shared key-value store across the run
        trigger_data    — data passed in from the trigger
    """

    def __init__(self, workflow_id: str, trigger_data: dict = None):
        self.run_id       = str(uuid.uuid4())
        self.workflow_id  = workflow_id
        self.started_at   = datetime.utcnow().isoformat()
        self.finished_at  = None
        self.status       = "running"
        self.node_results: Dict[str, Dict] = {}
        self.variables:    Dict[str, any]  = {}
        self.trigger_data = trigger_data or {}

    def set_node_pending(self, node_id: str):
        self.node_results[node_id] = {
            "status":      "pending",
            "started_at":  None,
            "duration_ms": None,
            "input":       None,
            "output":      None,
            "error":       None,
        }

    def start_node(self, node_id: str, inputs: dict):
        self.node_results[node_id]["status"]     = "running"
        self.node_results[node_id]["started_at"] = datetime.utcnow().isoformat()
        self.node_results[node_id]["input"]      = inputs

    def complete_node(self, node_id: str, output: dict, duration_ms: float):
        self.node_results[node_id]["status"]      = "success"
        self.node_results[node_id]["output"]      = output
        self.node_results[node_id]["duration_ms"] = round(duration_ms, 2)

    def fail_node(self, node_id: str, error: str, duration_ms: float):
        self.node_results[node_id]["status"]      = "failed"
        self.node_results[node_id]["error"]       = error
        self.node_results[node_id]["duration_ms"] = round(duration_ms, 2)

    def skip_node(self, node_id: str, reason: str):
        self.node_results[node_id]["status"] = "skipped"
        self.node_results[node_id]["error"]  = reason

    def to_dict(self) -> dict:
        return {
            "run_id":       self.run_id,
            "workflow_id":  self.workflow_id,
            "started_at":   self.started_at,
            "finished_at":  self.finished_at,
            "status":       self.status,
            "node_results": self.node_results,
            "variables":    self.variables,
        }


# ═══════════════════════════════════════════════════
# RUN PERSISTENCE (SQLite)
# ═══════════════════════════════════════════════════

_runs_table_created = False


def _init_runs_table():
    """Create the workflow_runs table. Idempotent."""
    global _runs_table_created
    if _runs_table_created:
        return

    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workflow_runs (
        run_id       TEXT PRIMARY KEY,
        workflow_id  TEXT NOT NULL,
        status       TEXT NOT NULL,
        started_at   TEXT NOT NULL,
        finished_at  TEXT,
        result       TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY (workflow_id) REFERENCES workflows(id)
    )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_workflow ON workflow_runs(workflow_id)"
    )
    conn.commit()
    _runs_table_created = True


def _persist_run(ctx: RunContext):
    """Save or update a run in the database."""
    _init_runs_table()

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO workflow_runs
            (run_id, workflow_id, status, started_at, finished_at, result)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        ctx.run_id,
        ctx.workflow_id,
        ctx.status,
        ctx.started_at,
        ctx.finished_at,
        json.dumps(ctx.to_dict()),
    ))
    conn.commit()


# ═══════════════════════════════════════════════════
# TOPOLOGICAL SORT (Kahn's Algorithm)
# ═══════════════════════════════════════════════════

def _topological_sort(nodes: list, edges: list) -> List[str]:
    """
    Kahn's algorithm for topological sorting.
    Returns a list of node_ids in execution order.
    Raises ValueError if the graph contains a cycle.
    """
    node_ids = {n["id"] for n in nodes}

    # Build adjacency list and in-degree count
    in_degree  = defaultdict(int)
    successors = defaultdict(list)

    for nid in node_ids:
        in_degree[nid] = 0  # Initialize all nodes

    for edge in edges:
        src = edge["source"]
        tgt = edge["target"]
        if src in node_ids and tgt in node_ids:
            successors[src].append(tgt)
            in_degree[tgt] += 1

    # Start with nodes that have no incoming edges
    queue = deque([nid for nid in node_ids if in_degree[nid] == 0])
    sorted_order = []

    while queue:
        nid = queue.popleft()
        sorted_order.append(nid)
        for successor in successors[nid]:
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                queue.append(successor)

    if len(sorted_order) != len(node_ids):
        raise ValueError(
            f"Workflow graph contains a cycle. "
            f"Sorted {len(sorted_order)} of {len(node_ids)} nodes."
        )

    return sorted_order


def _get_downstream_dependents(node_id: str, edges: list, all_node_ids: Set[str]) -> Set[str]:
    """
    Find all transitive dependents of a node (everything downstream).
    Used to skip nodes when an upstream node fails.
    """
    successors = defaultdict(list)
    for edge in edges:
        if edge["source"] in all_node_ids and edge["target"] in all_node_ids:
            successors[edge["source"]].append(edge["target"])

    dependents = set()
    stack = [node_id]
    while stack:
        current = stack.pop()
        for succ in successors.get(current, []):
            if succ not in dependents:
                dependents.add(succ)
                stack.append(succ)

    return dependents


# ═══════════════════════════════════════════════════
# INPUT ASSEMBLY (edge mappings)
# ═══════════════════════════════════════════════════

def _assemble_inputs(
    node_id: str,
    edges: list,
    ctx: RunContext,
    nodes_by_id: dict,
) -> dict:
    """
    Build the input dict for a node by mapping outputs from upstream nodes
    via edge connections.

    Edge mapping:
        edge.source      → upstream node id
        edge.target      → this node id
        edge.source_port → which output key from upstream
        edge.target_port → which input key on this node

    If source_port / target_port are not specified, the entire upstream
    output is passed as a single 'data' input.
    """
    inputs = {}

    # Find all edges targeting this node
    incoming = [e for e in edges if e["target"] == node_id]

    for edge in incoming:
        src_id   = edge["source"]
        src_port = edge.get("source_port", "")
        tgt_port = edge.get("target_port", "data")

        src_result = ctx.node_results.get(src_id, {})
        src_output = src_result.get("output")

        if src_output is None:
            continue

        if src_port and isinstance(src_output, dict) and src_port in src_output:
            inputs[tgt_port] = src_output[src_port]
        else:
            inputs[tgt_port] = src_output

    # For trigger nodes, inject trigger_data if no upstream edges
    node_def = nodes_by_id.get(node_id, {})
    node_type = node_def.get("type", "")
    if node_type.startswith("trigger.") and not incoming:
        inputs["trigger_data"] = ctx.trigger_data

    # Inject run variables into inputs so nodes can reference them
    inputs["_variables"] = dict(ctx.variables)

    return inputs


# ═══════════════════════════════════════════════════
# UNITY BRIDGE NOTIFICATIONS
# ═══════════════════════════════════════════════════

def _emit_activate(node_id: str, node_label: str):
    """Notify Unity that a node is now executing."""
    try:
        unity_bridge.send(SimCommand.activate_agent(node_label or node_id[:8]))
    except Exception as e:
        logger.debug(f"[Engine] Unity emit failed (activate): {e}")


def _emit_complete(node_id: str, node_label: str, output_preview: str = ""):
    """Notify Unity that a node completed successfully."""
    try:
        unity_bridge.send(SimCommand.complete_agent(node_label or node_id[:8], output_preview))
    except Exception as e:
        logger.debug(f"[Engine] Unity emit failed (complete): {e}")


def _emit_error(node_id: str, node_label: str, error: str):
    """Notify Unity that a node failed."""
    try:
        cmd = SimCommand(
            type=CommandType.AGENT_ERROR,
            payload={
                "agent_name": node_label or node_id[:8],
                "error": error[:200],
            }
        )
        unity_bridge.send(cmd)
    except Exception as e:
        logger.debug(f"[Engine] Unity emit failed (error): {e}")


def _emit_toast(message: str, level: str = "info"):
    """Send a toast notification to Unity."""
    try:
        unity_bridge.send(SimCommand.show_toast(message, level))
    except Exception:
        pass


# ═══════════════════════════════════════════════════
# MAIN ENGINE — run_workflow()
# ═══════════════════════════════════════════════════

def run_workflow(workflow_id: str, trigger_data: dict = None) -> dict:
    """
    Execute a workflow end-to-end.

    1. Load the workflow definition from workflow_store
    2. Topological sort the graph
    3. Execute each node in order, passing outputs via edges
    4. Handle failures: skip downstream dependents, continue independent branches
    5. Persist the run result to SQLite
    6. Emit Unity bridge updates at each step

    Args:
        workflow_id:  The ID of the workflow to run
        trigger_data: Optional data from the trigger (webhook body, etc.)

    Returns:
        Full run result dict (run_id, status, node_results, variables, timing)

    Raises:
        ValueError: If workflow not found or graph is invalid
    """
    # Load workflow
    workflow = workflow_store.get_workflow(workflow_id)
    if not workflow:
        raise ValueError(f"Workflow not found: {workflow_id}")

    graph = workflow.get("graph", {})
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        raise ValueError(f"Workflow '{workflow['name']}' has no nodes")

    # Build lookup
    nodes_by_id = {n["id"]: n for n in nodes}

    # Topological sort
    exec_order = _topological_sort(nodes, edges)

    # Create run context
    ctx = RunContext(workflow_id=workflow_id, trigger_data=trigger_data)

    # Initialize all nodes as pending
    for nid in exec_order:
        ctx.set_node_pending(nid)

    # Notify Unity
    _emit_toast(f"▶ Running workflow: {workflow['name']}", "info")

    # Persist initial state
    _persist_run(ctx)

    # Track which nodes to skip (downstream of failures)
    skip_set: Set[str] = set()
    all_node_ids = set(nodes_by_id.keys())
    has_failures = False

    # Execute nodes in topological order
    for node_id in exec_order:
        node_def = nodes_by_id[node_id]
        node_type  = node_def.get("type", "")
        node_label = node_def.get("label", node_type)
        node_params = node_def.get("params", {})

        # Skip if this node depends on a failed upstream node
        if node_id in skip_set:
            ctx.skip_node(node_id, "Skipped — upstream node failed")
            logger.info(f"[Engine] Skipping {node_label} ({node_id[:8]}) — upstream failed")
            continue

        # Assemble inputs from upstream outputs
        inputs = _assemble_inputs(node_id, edges, ctx, nodes_by_id)

        # Start node
        ctx.start_node(node_id, inputs)
        _emit_activate(node_id, node_label)
        logger.info(f"[Engine] Executing: {node_label} ({node_type})")

        start_ms = time.time() * 1000

        try:
            # Get the node definition from the library and execute
            lib_node = node_library.get_node(node_type)
            output = lib_node.execute(inputs, node_params)

            duration_ms = (time.time() * 1000) - start_ms

            # Handle set_variable signal
            if isinstance(output, dict) and output.get("_set_variable"):
                var_name  = output.get("variable_name")
                var_value = output.get("variable_value")
                if var_name:
                    ctx.variables[var_name] = var_value
                    logger.debug(f"[Engine] Variable set: {var_name} = {var_value}")

            ctx.complete_node(node_id, output, duration_ms)
            _emit_complete(node_id, node_label, str(output)[:120])
            logger.info(
                f"[Engine] ✓ {node_label} completed in {duration_ms:.0f}ms"
            )

        except Exception as e:
            duration_ms = (time.time() * 1000) - start_ms
            error_msg = str(e)

            ctx.fail_node(node_id, error_msg, duration_ms)
            has_failures = True

            _emit_error(node_id, node_label, error_msg)
            logger.error(f"[Engine] ✗ {node_label} failed: {error_msg}")

            # Skip all downstream dependents of this failed node
            downstream = _get_downstream_dependents(node_id, edges, all_node_ids)
            skip_set.update(downstream)
            if downstream:
                logger.info(
                    f"[Engine] Skipping {len(downstream)} downstream nodes "
                    f"due to {node_label} failure"
                )

        # Persist intermediate state
        _persist_run(ctx)

    # Determine final status
    statuses = [r["status"] for r in ctx.node_results.values()]
    if all(s == "success" for s in statuses):
        ctx.status = "success"
    elif all(s in ("failed", "skipped") for s in statuses):
        ctx.status = "failed"
    elif has_failures:
        ctx.status = "partial"
    else:
        ctx.status = "success"

    ctx.finished_at = datetime.utcnow().isoformat()

    # Final persist
    _persist_run(ctx)

    # Final Unity notification
    if ctx.status == "success":
        _emit_toast(f"✓ Workflow '{workflow['name']}' completed successfully", "success")
    elif ctx.status == "partial":
        _emit_toast(f"⚠ Workflow '{workflow['name']}' completed with errors", "warning")
    else:
        _emit_toast(f"✗ Workflow '{workflow['name']}' failed", "error")

    logger.info(
        f"[Engine] Workflow run {ctx.run_id[:8]} finished: {ctx.status} "
        f"({len(exec_order)} nodes)"
    )

    return ctx.to_dict()


# ═══════════════════════════════════════════════════
# RUN RETRIEVAL
# ═══════════════════════════════════════════════════

def get_run(run_id: str) -> Optional[Dict]:
    """
    Retrieve a single run result by run_id.
    Returns None if not found.
    """
    _init_runs_table()

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT result FROM workflow_runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()

    if not row:
        return None

    return json.loads(row["result"])


def list_runs(workflow_id: str) -> List[Dict]:
    """
    List all runs for a workflow, newest first.
    Returns a summary for each run (not the full node_results).
    """
    _init_runs_table()

    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT run_id, status, started_at, finished_at FROM workflow_runs "
        "WHERE workflow_id = ? ORDER BY started_at DESC",
        (workflow_id,)
    )

    runs = []
    for row in cursor.fetchall():
        runs.append({
            "run_id":      row["run_id"],
            "workflow_id": workflow_id,
            "status":      row["status"],
            "started_at":  row["started_at"],
            "finished_at": row["finished_at"],
        })

    return runs
