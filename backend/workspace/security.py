"""
security.py — path sandbox for the workspace engine.

Every filesystem operation resolves through WorkspaceSecurity.resolve().
Guarantees:
    - no escape outside the workspace root (symlinks + .. both handled)
    - protected paths (.git internals, checkpoint store) never written
    - ignored dirs (node_modules, .next, __pycache__, venv) never indexed
"""

import os
from pathlib import Path

IGNORED_DIRS = {
    "node_modules", ".next", "__pycache__", ".git", ".venv", "venv",
    "dist", "build", ".turbo", ".vercel", ".xoltra_checkpoints",
    ".pytest_cache", ".mypy_cache", "coverage",
}

IGNORED_FILES = {".DS_Store", "Thumbs.db"}

# Files the agent may read but must never write/delete autonomously.
PROTECTED_WRITE = {".env", ".env.local", ".env.production"}

MAX_FILE_BYTES = 2 * 1024 * 1024  # refuse to load >2MB files into memory

TEXT_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".md",
    ".css", ".scss", ".html", ".yml", ".yaml", ".toml", ".txt", ".env",
    ".gitignore", ".sql", ".sh", ".svg", ".xml", ".ini", ".cfg",
}


class WorkspaceSecurityError(Exception):
    """Raised when an operation would leave the sandbox or touch a protected path."""


class WorkspaceSecurity:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise WorkspaceSecurityError(f"Workspace root does not exist: {root}")

    def resolve(self, rel_path: str, for_write: bool = False) -> Path:
        """Resolve a workspace-relative path. Raises on sandbox escape."""
        if not rel_path or rel_path.strip() in ("", ".", "/"):
            raise WorkspaceSecurityError("Empty path")
        candidate = (self.root / rel_path.lstrip("/\\")).resolve()
        if not candidate.is_relative_to(self.root):
            raise WorkspaceSecurityError(f"Path escapes workspace: {rel_path}")
        rel = candidate.relative_to(self.root)
        for part in rel.parts[:-1]:
            if part in IGNORED_DIRS:
                raise WorkspaceSecurityError(f"Path inside protected dir: {rel_path}")
        if for_write:
            if candidate.name in PROTECTED_WRITE:
                raise WorkspaceSecurityError(f"Protected file, write refused: {rel_path}")
            if rel.parts and rel.parts[0] == ".git":
                raise WorkspaceSecurityError("Direct .git writes refused")
        return candidate

    def relpath(self, abs_path: Path) -> str:
        return abs_path.relative_to(self.root).as_posix()

    def is_indexable(self, path: Path) -> bool:
        if path.name in IGNORED_FILES:
            return False
        if path.suffix.lower() not in TEXT_EXTENSIONS and path.suffix != "":
            return False
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                return False
        except OSError:
            return False
        return True
