"""
mcp_server.py — Xoltra MCP Server for Codex/Antigravity/VS Code Auto-Pairing

Implements the Model Context Protocol (MCP) to expose Xoltra's features
(knowledge, pipeline, workspace, projects, memory) to external editors.
Auto-detects and pairs when the companion extension is active.

Protocol: stdio-based JSON-RPC 2.0 per MCP spec.
"""
import os
import sys
import json
import uuid
import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── MCP Protocol Constants ──────────────────────────────
MCP_VERSION = "2024-11-05"
SERVER_NAME = "xoltra-mcp"
SERVER_VERSION = "1.0.0"

# ── Tool Definitions ────────────────────────────────────
TOOLS = [
    {
        "name": "xoltra_knowledge_query",
        "description": "Query Xoltra's knowledge base for context, insights, and past work relevant to the current task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query to search the knowledge base"},
                "mode": {"type": "string", "enum": ["fast", "thinking"], "default": "fast"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20}
            },
            "required": ["query"]
        }
    },
    {
        "name": "xoltra_run_pipeline",
        "description": "Execute Xoltra's multi-agent pipeline (Architect → Coder → Judge → Tester) on a goal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The goal or task to execute"},
                "mode": {"type": "string", "enum": ["default", "coach"], "default": "default"},
                "role_id": {"type": "string", "default": "default"},
                "answers": {"type": "object", "description": "Clarification answers if any"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "xoltra_workspace_read",
        "description": "Read a file from Xoltra's workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path in the workspace"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "xoltra_workspace_write",
        "description": "Write/create a file in Xoltra's workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "content": {"type": "string", "description": "File content"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "xoltra_workspace_search",
        "description": "Search across the workspace (symbol, path, content).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "xoltra_project_context",
        "description": "Get project context including structure, docs, and conversation digests.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "query": {"type": "string", "description": "Optional query for relevant chunks"}
            },
            "required": ["project_id"]
        }
    },
    {
        "name": "xoltra_memory_store",
        "description": "Store a memory/insight in Xoltra's knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to store"},
                "node_type": {"type": "string", "enum": ["goal", "insight", "document", "workflow"], "default": "insight"},
                "title": {"type": "string", "description": "Optional title"}
            },
            "required": ["content"]
        }
    },
    {
        "name": "xoltra_git_commit",
        "description": "Commit and push changes to GitHub from the workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message"},
                "paths": {"type": "array", "items": {"type": "string"}, "description": "Optional specific file paths"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "xoltra_usage_summary",
        "description": "Get current token usage and plan summary.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

# ── MCP Server Core ─────────────────────────────────────

class XoltraMCPServer:
    """JSON-RPC 2.0 MCP server bridging Xoltra to external IDEs."""

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self._initialized = False
        self._client_capabilities: Dict[str, Any] = {}
        self._workspace_engine = None
        self._pipeline = None

    def _get_workspace_engine(self):
        if self._workspace_engine is None:
            from workspace_routes import _get_engine
            self._workspace_engine = _get_engine()
        return self._workspace_engine

    def _get_pipeline(self):
        if self._pipeline is None:
            from pipeline import get_pipeline
            self._pipeline = get_pipeline()
        return self._pipeline

    def handle_message(self, raw: str) -> Optional[str]:
        """Process a single JSON-RPC message, return response or None for notifications."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return self._error(None, -32700, "Parse error")

        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return self._error(msg.get("id"), -32600, "Invalid Request")

        method = msg.get("method", "")
        req_id = msg.get("id")
        params = msg.get("params", {})

        # Notifications (no id) — no response
        is_notification = req_id is None

        try:
            result = self._dispatch(method, params)
            if is_notification:
                return None
            return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result})
        except MCPError as e:
            if is_notification:
                return None
            return self._error(req_id, e.code, e.message, e.data)
        except Exception as e:
            logger.error(f"[MCP] Unhandled error in {method}: {e}")
            if is_notification:
                return None
            return self._error(req_id, -32603, f"Internal error: {e}")

    def _dispatch(self, method: str, params: dict) -> Any:
        handlers = {
            "initialize": self._handle_initialize,
            "initialized": self._handle_initialized,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "ping": self._handle_ping,
        }
        handler = handlers.get(method)
        if handler is None:
            raise MCPError(-32601, f"Method not found: {method}")
        return handler(params)

    # ── Lifecycle ──────────────────────────────────────

    def _handle_initialize(self, params: dict) -> dict:
        self._pending_capabilities = params.get("capabilities", {})
        return {
            "protocolVersion": MCP_VERSION,
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION
            },
            "capabilities": {
                "tools": {},
                "resources": {}
            }
        }

    def _handle_initialized(self, params: dict) -> dict:
        self._initialized = True
        logger.info("[MCP] Client initialized, Xoltra bridge active")
        return {}

    def _handle_ping(self, params: dict) -> dict:
        return {}

    # ---- Tools ──────────────────────────────────────────

    def _handle_tools_list(self, params: dict) -> dict:
        return {"tools": TOOLS}

    def _handle_tools_call(self, params: dict) -> dict:
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        tool_handlers = {
            "xoltra_knowledge_query": self._tool_knowledge_query,
            "xoltra_run_pipeline": self._tool_run_pipeline,
            "xoltra_workspace_read": self._tool_workspace_read,
            "xoltra_workspace_write": self._tool_workspace_write,
            "xoltra_workspace_search": self._tool_workspace_search,
            "xoltra_project_context": self._tool_project_context,
            "xoltra_memory_store": self._tool_memory_store,
            "xoltra_git_commit": self._tool_git_commit,
            "xoltra_usage_summary": self._tool_usage_summary,
        }

        handler = tool_handlers.get(tool_name)
        if handler is None:
            raise MCPError(-32602, f"Unknown tool: {tool_name}")

        result = handler(arguments)
        return {
            "content": [
                {"type": "text", "text": json.dumps(result) if isinstance(result, dict) else str(result)}
            ]
        }

    # ---- Tool Implementations ───────────────────────────

    def _tool_knowledge_query(self, args: dict) -> dict:
        import xoltra_knowledge_engine as xke
        query = args["query"]
        mode = args.get("mode", "fast")
        top_k = args.get("top_k", 6)
        nodes = xke.get_context_by_mode(self.user_id, query, mode=mode)
        return {
            "nodes": [{
                "type": n.get("type"),
                "summary": n.get("content", {}).get("title", "")[:200],
                "relevance": round(n.get("relevance", 0), 3)
            } for n in nodes[:top_k]],
            "count": min(len(nodes), top_k)
        }

    def _tool_run_pipeline(self, args: dict) -> dict:
        pipeline = self._get_pipeline()
        result = pipeline.run(
            self.user_id,
            args["goal"],
            mode=args.get("mode", "default"),
            answers=args.get("answers", {}),
            role_id=args.get("role_id", "default")
        )
        return {
            "output": result.get("output", ""),
            "mode": result.get("mode"),
            "critic_status": result.get("critic_status"),
            "error": result.get("error")
        }

    def _tool_workspace_read(self, args: dict) -> dict:
        e = self._get_workspace_engine()
        content = e["fs"].read_file(args["path"])
        return {"path": args["path"], "content": content}

    def _tool_workspace_write(self, args: dict) -> dict:
        e = self._get_workspace_engine()
        patch = e["patcher"].propose(
            f"MCP: Write {args['path']}",
            [{"type": "write", "path": args["path"], "content": args["content"]}],
            auto_update_imports=False
        )
        e["patcher"].apply(patch["id"])
        e["indexer"].invalidate(args["path"])
        return {"path": args["path"], "status": "written"}

    def _tool_workspace_search(self, args: dict) -> dict:
        e = self._get_workspace_engine()
        if not e["indexer"].files:
            e["indexer"].build()
        results = e["indexer"].search(args["query"])
        return {"results": results[:20], "count": len(results)}

    def _tool_project_context(self, args: dict) -> dict:
        import knowledge_db as kdb
        conn = kdb._get_conn()
        row = conn.execute(
            "SELECT structure_summary, key_docs_summary, conversation_digests FROM project_cache WHERE project_id = ?",
            (args["project_id"],)
        ).fetchone()
        if not row:
            return {"error": "Project not found"}
        return {
            "structure_summary": row["structure_summary"],
            "key_docs_summary": row["key_docs_summary"],
            "digests": json.loads(row["conversation_digests"])[-5:]
        }

    def _tool_memory_store(self, args: dict) -> dict:
        import knowledge_db as kdb
        node_id = kdb.create_node(
            self.user_id,
            node_type=args.get("node_type", "insight"),
            content={"title": args.get("title", ""), "body": args["content"]},
            status="active"
        )
        return {"node_id": node_id, "status": "stored"}

    def _tool_git_commit(self, args: dict) -> dict:
        e = self._get_workspace_engine()
        result = e["terminal"].git_commit(args["message"], paths=args.get("paths"))
        push_result = e["terminal"].git_push("origin")
        return {"commit": result, "push": push_result}

    def _tool_usage_summary(self, args: dict) -> dict:
        import subscription_manager as sm
        return sm.get_usage_summary(self.user_id)

    # ---- Resources ──────────────────────────────────────

    def _handle_resources_list(self, params: dict) -> dict:
        return {"resources": [
            {"uri": "xoltra://knowledge/stats", "name": "Knowledge Stats", "mimeType": "application/json"},
            {"uri": "xoltra://workspace/tree", "name": "Workspace Tree", "mimeType": "application/json"},
            {"uri": "xoltra://projects/list", "name": "Projects List", "mimeType": "application/json"},
        ]}

    def _handle_resources_read(self, params: dict) -> dict:
        uri = params.get("uri", "")
        if uri == "xoltra://knowledge/stats":
            import knowledge_db as kdb
            stats = kdb.get_stats(self.user_id)
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(stats)}]}
        elif uri == "xoltra://workspace/tree":
            e = self._get_workspace_engine()
            tree = e["fs"].tree()
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(tree)}]}
        elif uri == "xoltra://projects/list":
            import knowledge_db as kdb
            rows = kdb._get_conn().execute(
                "SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC",
                (self.user_id,)
            ).fetchall()
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps([dict(r) for r in rows])}]}
        raise MCPError(-32602, f"Unknown resource: {uri}")

    # ---- Helpers ────────────────────────────────────────

    def _json(self, req_id, result):
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result})

    def _error(self, req_id, code, message, data=None):
        err = {"code": code, "message": message}
        if data:
            err["data"] = data
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "error": err})


class MCPError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


# ── STDIO Transport ────────────────────────────────────────

def run_stdio():
    """Run MCP server over stdio — the standard MCP transport for IDE integration."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [MCP] %(message)s")
    logger.info("Xoltra MCP Server starting on stdio")

    # Extract user_id from env (set by the IDE/extension)
    user_id = os.environ.get("XOLTRA_USER_ID")
    server = XoltraMCPServer(user_id=user_id)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        response = server.handle_message(line)
        if response:
            sys.stdout.write(response + "\n")
            sys.stdout.flush()


# ── HTTP Transport (for web-based IDEs like Codex/Antigravity) ──

def create_mcp_blueprint():
    """Create a Flask blueprint for MCP over HTTP (SSE + POST)."""
    from flask import Blueprint, request, jsonify, Response
    import queue, threading

    mcp_bp = Blueprint("mcp", __name__, url_prefix="/api/mcp")

    @mcp_bp.route("/message", methods=["POST"])
    def mcp_message():
        """Single JSON-RPC message endpoint."""
        from auth import require_auth, get_current_user_id
        user_id = get_current_user_id()
        server = XoltraMCPServer(user_id=user_id)
        raw = request.get_data(as_text=True)
        response = server.handle_message(raw)
        if response:
            return jsonify(json.loads(response))
        return "", 204

    @mcp_bp.route("/sse", methods=["GET"])
    def mcp_sse():
        """SSE endpoint for streaming MCP communication (Codex/Antigravity style)."""
        from auth import require_auth, get_current_user_id
        user_id = get_current_user_id()
        server = XoltraMCPServer(user_id=user_id)

        def generate():
            # Send endpoint event for POST back
            yield f"event: endpoint\ndata: /api/mcp/message\n\n"
            # Keep alive
            import time
            while True:
                yield f": keepalive\n\n"
                time.sleep(15)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    logger.info("[MCP] HTTP transport registered at /api/mcp")
    return mcp_bp


# ── Auto-Discovery Manifest ────────────────────────────────

def generate_manifest(port: int = 5001) -> dict:
    """Generate the MCP server manifest for IDE auto-discovery."""
    return {
        "name": SERVER_NAME,
        "version": SERVER_VERSION,
        "description": "Xoltra AI — Multi-agent knowledge, pipeline, and workspace server",
        "vendor": "Xoltra",
        "transports": {
            "stdio": {
                "command": sys.executable,
                "args": ["-m", "backend.mcp_server"]
            },
            "http": {
                "url": f"http://localhost:{port}/api/mcp/message",
                "sse_url": f"http://localhost:{port}/api/mcp/sse"
            }
        },
        "capabilities": {
            "tools": True,
            "resources": True
        },
        "tools": TOOLS
    }


if __name__ == "__main__":
    run_stdio()