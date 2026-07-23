"""
workspace — Xoltra Autonomous Workspace Manipulation engine.

Modules:
    security     — path sandboxing + ignore rules (every fs touch goes through this)
    fs_ops       — create/read/edit/rename/move/delete files & folders
    indexer      — repository scan, file index, language detection
    dep_graph    — import parsing, dependency graph, reference updates
    search       — symbol + keyword search over the index
    semantic     — embedding-based semantic search (Cohere, lexical fallback)
    checkpoints  — snapshot/rollback transaction journal
    patcher      — diff generation, syntax validation, atomic multi-file apply
    terminal     — allowlisted command execution + git operations
    tasks        — concurrent task manager + mutation lock + change feed
    agent        — NL instruction → plan → validated patch (streams steps)

Register API with:
    from workspace_routes import register_workspace_routes
    register_workspace_routes(app)
"""

from workspace.security import WorkspaceSecurity, WorkspaceSecurityError
from workspace.fs_ops import FsOps
from workspace.indexer import RepoIndexer
from workspace.dep_graph import DependencyGraph
from workspace.checkpoints import CheckpointStore
from workspace.patcher import Patcher, PatchValidationError
from workspace.terminal import Terminal, TerminalError
from workspace.semantic import SemanticSearch
from workspace.tasks import TaskManager, ChangeFeed, MUTATION_LOCK
from workspace.agent import WorkspaceAgent

__all__ = [
    "WorkspaceSecurity", "WorkspaceSecurityError",
    "FsOps", "RepoIndexer", "DependencyGraph",
    "CheckpointStore", "Patcher", "PatchValidationError",
    "Terminal", "TerminalError", "SemanticSearch",
    "TaskManager", "ChangeFeed", "MUTATION_LOCK", "WorkspaceAgent",
]
