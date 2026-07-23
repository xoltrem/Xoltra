"""
agent.py — natural-language instruction -> plan -> validated patch.

Flow (each step streamed to the frontend via on_step):
    1. index      — refresh repo index + dependency graph
    2. plan       — call_architect: task -> ordered file operations
    3. generate   — call_coding: full new content per changed file
    4. propose    — Patcher.propose (diffs + syntax + reference validation)
    5. (frontend approves) -> /api/workspace/patches/<id>/apply

Reuses llm.py's existing role infrastructure — no new LLM plumbing.
The agent never applies a patch itself: approval stays with the user
unless auto_apply=True is passed explicitly.
"""

import json
import logging
from typing import Callable, Dict, List, Optional

from workspace.security import WorkspaceSecurity
from workspace.fs_ops import FsOps
from workspace.indexer import RepoIndexer
from workspace.dep_graph import DependencyGraph
from workspace.patcher import Patcher, PatchValidationError

logger = logging.getLogger(__name__)

MAX_CONTEXT_FILES = 12
MAX_FILE_CHARS = 24_000

_PLAN_PROMPT = """You are the workspace planner for the Xoltra repository.
Convert the user's instruction into concrete file operations.

REPOSITORY MAP (path [language] — top symbols):
{repo_map}

USER INSTRUCTION:
{instruction}

Respond ONLY with JSON:
{{
  "summary": "one-line description of the change",
  "reasoning": "brief why/how",
  "context_files": ["paths the code generator must read first"],
  "operations": [
    {{"type": "write", "path": "...", "intent": "what to create/change in this file"}},
    {{"type": "delete", "path": "..."}},
    {{"type": "move", "path": "...", "to": "..."}},
    {{"type": "mkdir", "path": "..."}}
  ]
}}
Rules: paths are workspace-relative; prefer editing existing files over new ones;
respect existing architecture; list every file that needs changes."""

_CODE_PROMPT = """You are the code generator for the Xoltra repository.
Produce the COMPLETE new content of one file.

TASK: {summary}
FILE: {path}
INTENT: {intent}

CURRENT CONTENT OF {path} (empty if new file):
----------------
{current}
----------------

RELATED FILES FOR CONTEXT:
{context}

Rules:
- Output ONLY the full file content. No markdown fences, no commentary.
- Match the existing style, naming, and imports of the repository.
- Keep all existing behavior unless the intent says to change it."""


class WorkspaceAgent:
    def __init__(self, security: WorkspaceSecurity, fs: FsOps,
                 indexer: RepoIndexer, deps: DependencyGraph, patcher: Patcher):
        self.sec = security
        self.fs = fs
        self.indexer = indexer
        self.deps = deps
        self.patcher = patcher

    def run(self, instruction: str,
            on_step: Optional[Callable[[str, Dict], None]] = None,
            auto_apply: bool = False) -> Dict:
        # deferred import: keeps workspace core importable without LLM deps
        # (llm.py needs cohere/env keys; tests and CLI tools don't)
        from llm import call_architect, call_coding, safe_json_parse  # noqa: F401
        self._call_architect, self._call_coding, self._safe_json_parse = (
            call_architect, call_coding, safe_json_parse)
        emit = on_step or (lambda name, data: None)

        emit("index", {"detail": "Scanning repository"})
        stats = self.indexer.build()
        self.deps.build()
        emit("index", {"detail": f"{stats['files']} files indexed", "done": True})

        emit("plan", {"detail": "Planning changes"})
        plan = self._plan(instruction)
        emit("plan", {"detail": plan["summary"], "reasoning": plan.get("reasoning", ""),
                      "operations": plan["operations"], "done": True})

        context = self._load_context(plan.get("context_files", []))

        ops: List[Dict] = []
        for op in plan["operations"]:
            if op["type"] == "write":
                emit("generate", {"detail": f"Writing {op['path']}"})
                content = self._generate(plan["summary"], op, context)
                ops.append({"type": "write", "path": op["path"], "content": content})
            else:
                ops.append({k: v for k, v in op.items() if k != "intent"})
        emit("generate", {"detail": f"{len(ops)} operations ready", "done": True})

        emit("validate", {"detail": "Building diffs, checking syntax and references"})
        try:
            patch = self.patcher.propose(plan["summary"], ops)
        except PatchValidationError as e:
            emit("validate", {"detail": str(e), "error": True})
            raise
        emit("validate", {"detail": "Patch valid", "patch_id": patch["id"], "done": True})

        if auto_apply:
            emit("apply", {"detail": "Applying patch"})
            patch = self.patcher.apply(patch["id"])
            self.indexer.build()
            self.deps.build()
            emit("apply", {"detail": "Applied", "checkpoint_id": patch["checkpoint_id"], "done": True})

        return {"plan": plan, "patch": patch}

    # ── internals ──────────────────────────────────────────

    def _plan(self, instruction: str) -> Dict:
        raw = self._call_architect(_PLAN_PROMPT.format(
            repo_map=self.indexer.project_summary(),
            instruction=instruction,
        ))
        plan = self._safe_json_parse(raw)
        if not isinstance(plan, dict) or not plan.get("operations"):
            raise PatchValidationError(f"Planner returned no operations: {str(raw)[:300]}")
        for op in plan["operations"]:
            if op.get("type") not in ("write", "delete", "move", "mkdir"):
                raise PatchValidationError(f"Planner produced invalid op: {op}")
            self.sec.resolve(op["path"], for_write=True)  # sandbox check up front
            if op["type"] == "move":
                self.sec.resolve(op["to"], for_write=True)
        return plan

    def _load_context(self, paths: List[str]) -> str:
        chunks = []
        for rel in paths[:MAX_CONTEXT_FILES]:
            try:
                src = self.fs.read_file(rel)[:MAX_FILE_CHARS]
                chunks.append(f"=== {rel} ===\n{src}")
            except (FileNotFoundError, Exception):
                continue
        return "\n\n".join(chunks) if chunks else "(none)"

    def _generate(self, summary: str, op: Dict, context: str) -> str:
        try:
            current = self.fs.read_file(op["path"])[:MAX_FILE_CHARS]
        except Exception:
            current = ""
        raw = self._call_coding(_CODE_PROMPT.format(
            summary=summary, path=op["path"],
            intent=op.get("intent", ""), current=current, context=context,
        ))
        content = raw.strip()
        # strip accidental markdown fences
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        return content + ("\n" if not content.endswith("\n") else "")
