"""
patcher.py — diff generation, validation, atomic multi-file apply.

Patch shape (also what the frontend approval UI consumes):
{
  "id": "...", "title": "...", "status": "proposed|applied|rolled_back",
  "checkpoint_id": "...",
  "operations": [
    {"type": "write",  "path": "...", "content": "..."},
    {"type": "delete", "path": "..."},
    {"type": "move",   "path": "...", "to": "..."},
    {"type": "mkdir",  "path": "..."}
  ],
  "diffs": [{"path": "...", "diff": "<unified>"}]
}

apply() is transactional: snapshot every touched path first, validate all
syntax, then execute; any failure mid-apply triggers automatic rollback.
"""

import ast
import difflib
import json
import re
import time
import uuid
from typing import Dict, List, Optional

from workspace.security import WorkspaceSecurity
from workspace.fs_ops import FsOps
from workspace.checkpoints import CheckpointStore
from workspace.dep_graph import DependencyGraph
from workspace.tasks import MUTATION_LOCK


class PatchValidationError(Exception):
    pass


def _validate_syntax(path: str, content: str) -> Optional[str]:
    """Return error string or None. Python via ast; JSON via json;
    TS/JS via cheap structural checks (balanced braces/brackets/parens
    outside strings) — full TS checking belongs to the repo's own tsc/eslint."""
    if path.endswith(".py"):
        try:
            ast.parse(content)
        except SyntaxError as e:
            return f"Python syntax error line {e.lineno}: {e.msg}"
        return None
    if path.endswith(".json"):
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            return f"JSON error line {e.lineno}: {e.msg}"
        return None
    if re.search(r"\.(tsx?|jsx?|mjs|cjs)$", path):
        stripped = re.sub(r"//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`",
                         "", content, flags=re.DOTALL)
        for open_c, close_c in (("{", "}"), ("(", ")"), ("[", "]")):
            if stripped.count(open_c) != stripped.count(close_c):
                return f"Unbalanced {open_c}{close_c} in {path}"
    return None


class Patcher:
    def __init__(self, security: WorkspaceSecurity, fs: FsOps,
                 checkpoints: CheckpointStore, dep_graph: DependencyGraph,
                 change_feed=None):
        self.sec = security
        self.fs = fs
        self.cp = checkpoints
        self.deps = dep_graph
        self.feed = change_feed
        self.patches: Dict[str, Dict] = {}

    # ── propose ────────────────────────────────────────────

    def propose(self, title: str, operations: List[Dict],
                auto_update_imports: bool = True) -> Dict:
        """Build a patch: expand move ops with import rewrites, generate
        diffs, validate syntax. Does NOT touch the filesystem."""
        ops = list(operations)

        if auto_update_imports:
            extra: List[Dict] = []
            for op in operations:
                if op["type"] == "move":
                    rewrites = self.deps.rewrite_imports_for_move(op["path"], op["to"])
                    for path, content in rewrites.items():
                        if not any(o["type"] == "write" and o["path"] == path for o in ops):
                            extra.append({"type": "write", "path": path, "content": content,
                                          "reason": f"import update for move {op['path']} -> {op['to']}"})
            ops.extend(extra)

        errors, diffs = [], []
        for op in ops:
            if op["type"] == "write":
                err = _validate_syntax(op["path"], op["content"])
                if err:
                    errors.append(err)
                diffs.append({"path": op["path"], "diff": self._diff(op["path"], op["content"])})
            elif op["type"] == "delete":
                dependents = self.deps.dependents_of(op["path"])
                survivors = [d for d in dependents
                             if not any(o["type"] == "delete" and o["path"] == d for o in ops)]
                if survivors:
                    errors.append(f"Deleting {op['path']} breaks imports in: {', '.join(survivors[:5])}")
                diffs.append({"path": op["path"], "diff": self._diff(op["path"], None)})
            elif op["type"] == "move":
                diffs.append({"path": op["path"],
                              "diff": f"--- a/{op['path']}\n+++ b/{op['to']}\n(rename)"})
            elif op["type"] == "mkdir":
                diffs.append({"path": op["path"], "diff": f"+++ b/{op['path']}/ (new folder)"})
            else:
                errors.append(f"Unknown op type: {op.get('type')}")

        if errors:
            raise PatchValidationError("; ".join(errors))

        patch = {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "created": time.time(),
            "status": "proposed",
            "checkpoint_id": None,
            "operations": ops,
            "diffs": diffs,
        }
        self.patches[patch["id"]] = patch
        return patch

    def _diff(self, path: str, new_content: Optional[str]) -> str:
        try:
            old = self.fs.read_file(path)
        except (FileNotFoundError, Exception):
            old = ""
        old_lines = old.splitlines(keepends=True)
        new_lines = (new_content or "").splitlines(keepends=True)
        return "".join(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{path}", tofile=f"b/{path}" if new_content is not None else "/dev/null",
        ))

    # ── apply ──────────────────────────────────────────────

    def apply(self, patch_id: str) -> Dict:
        patch = self.patches.get(patch_id)
        if not patch:
            raise KeyError(f"Patch not found: {patch_id}")
        if patch["status"] == "applied":
            return patch

        # serialize all mutations — two concurrent applies never interleave
        with MUTATION_LOCK:
            touched: List[str] = []
            for op in patch["operations"]:
                touched.append(op["path"])
                if op["type"] == "move":
                    touched.append(op["to"])
            patch["checkpoint_id"] = self.cp.snapshot(sorted(set(touched)), label=patch["title"])

            try:
                results = []
                for op in patch["operations"]:
                    if op["type"] == "write":
                        results.append(self.fs.write_file(op["path"], op["content"]))
                    elif op["type"] == "delete":
                        results.append(self.fs.delete(op["path"]))
                    elif op["type"] == "move":
                        results.append(self.fs.move(op["path"], op["to"]))
                    elif op["type"] == "mkdir":
                        results.append(self.fs.create_folder(op["path"]))
                patch["status"] = "applied"
                patch["results"] = results
            except Exception as e:
                self.cp.rollback(patch["checkpoint_id"])
                patch["status"] = "failed"
                raise PatchValidationError(f"Apply failed, rolled back: {e}") from e

        if self.feed:
            self.feed.emit("patch_applied", {"patch_id": patch_id, "title": patch["title"],
                                             "paths": sorted(set(touched))})
        return patch

    def rollback(self, patch_id: str) -> Dict:
        patch = self.patches.get(patch_id)
        if not patch or not patch.get("checkpoint_id"):
            raise KeyError(f"No applied patch to roll back: {patch_id}")
        with MUTATION_LOCK:
            result = self.cp.rollback(patch["checkpoint_id"])
            patch["status"] = "rolled_back"
        if self.feed:
            self.feed.emit("patch_rolled_back", {"patch_id": patch_id,
                                                 "paths": result["restored"] + result["deleted"]})
        return {"patch": patch_id, **result}
