"""
fs_ops.py — sandboxed filesystem operations.

All mutations return an OpResult dict so callers (routes, agent, checkpoints)
get a uniform shape:  {"op", "path", "ok", "detail"}.
Mutations do NOT snapshot by themselves — the Patcher/CheckpointStore wraps
them so a multi-file change is one atomic, rollbackable transaction.
"""

import shutil
from pathlib import Path
from typing import List, Dict, Optional

from workspace.security import WorkspaceSecurity, WorkspaceSecurityError, IGNORED_DIRS


class FsOps:
    def __init__(self, security: WorkspaceSecurity):
        self.sec = security

    # ── reads ──────────────────────────────────────────────

    def read_file(self, rel_path: str) -> str:
        p = self.sec.resolve(rel_path)
        if not p.is_file():
            raise FileNotFoundError(rel_path)
        return p.read_text(encoding="utf-8", errors="replace")

    def exists(self, rel_path: str) -> bool:
        try:
            return self.sec.resolve(rel_path).exists()
        except WorkspaceSecurityError:
            return False

    def tree(self, rel_path: str = ".", max_depth: int = 12) -> List[Dict]:
        """Nested file-tree for the explorer UI."""
        root = self.sec.resolve(rel_path) if rel_path != "." else self.sec.root

        def walk(d: Path, depth: int) -> List[Dict]:
            if depth > max_depth:
                return []
            out = []
            try:
                entries = sorted(d.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
            except OSError:
                return []
            for e in entries:
                if e.name in IGNORED_DIRS or e.name.startswith(".git"):
                    continue
                node = {"name": e.name, "path": self.sec.relpath(e), "type": "dir" if e.is_dir() else "file"}
                if e.is_dir():
                    node["children"] = walk(e, depth + 1)
                else:
                    try:
                        node["size"] = e.stat().st_size
                    except OSError:
                        node["size"] = 0
                out.append(node)
            return out

        return walk(root, 0)

    # ── mutations ──────────────────────────────────────────

    def write_file(self, rel_path: str, content: str) -> Dict:
        p = self.sec.resolve(rel_path, for_write=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"op": "write", "path": rel_path, "ok": True, "detail": f"{len(content)} chars"}

    def create_folder(self, rel_path: str) -> Dict:
        p = self.sec.resolve(rel_path, for_write=True)
        p.mkdir(parents=True, exist_ok=True)
        return {"op": "mkdir", "path": rel_path, "ok": True, "detail": ""}

    def delete(self, rel_path: str) -> Dict:
        p = self.sec.resolve(rel_path, for_write=True)
        if not p.exists():
            raise FileNotFoundError(rel_path)
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"op": "delete", "path": rel_path, "ok": True, "detail": ""}

    def move(self, src: str, dst: str) -> Dict:
        """Rename/move a file or folder inside the sandbox."""
        s = self.sec.resolve(src, for_write=True)
        d = self.sec.resolve(dst, for_write=True)
        if not s.exists():
            raise FileNotFoundError(src)
        if d.exists():
            raise FileExistsError(dst)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        return {"op": "move", "path": src, "ok": True, "detail": f"-> {dst}"}
