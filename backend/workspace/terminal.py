"""
terminal.py — allowlisted command execution inside the workspace.

Not a general shell. Only commands whose first token is on the allowlist
run, cwd pinned to workspace root, no shell=True (no interpolation),
timeout enforced, output captured + size-capped.

Git helpers wrap the common flows (status/add/commit/push/pull/branch)
so the agent and the UI don't build raw argv themselves.
"""

import shlex
import subprocess
from typing import Dict, List, Optional

from workspace.security import WorkspaceSecurity

ALLOWED_COMMANDS = {
    "git", "npm", "npx", "node", "python", "python3", "pip",
    "pytest", "tsc", "eslint", "next", "vercel", "ls", "dir",
}

BLOCKED_GIT_SUBCOMMANDS = {"daemon", "instaweb"}

TIMEOUT_S = 120
MAX_OUTPUT = 64_000


class TerminalError(Exception):
    pass


class Terminal:
    def __init__(self, security: WorkspaceSecurity):
        self.sec = security

    def run(self, command: str, timeout: int = TIMEOUT_S) -> Dict:
        try:
            argv = shlex.split(command)
        except ValueError as e:
            raise TerminalError(f"Bad command syntax: {e}")
        if not argv:
            raise TerminalError("Empty command")
        prog = argv[0].lower()
        if prog not in ALLOWED_COMMANDS:
            raise TerminalError(f"Command not allowed: {prog}. Allowed: {sorted(ALLOWED_COMMANDS)}")
        if prog == "git" and len(argv) > 1 and argv[1] in BLOCKED_GIT_SUBCOMMANDS:
            raise TerminalError(f"git {argv[1]} not allowed")
        try:
            proc = subprocess.run(
                argv, cwd=str(self.sec.root), capture_output=True,
                text=True, timeout=min(timeout, 300),
            )
        except subprocess.TimeoutExpired:
            raise TerminalError(f"Timed out after {timeout}s: {command}")
        except FileNotFoundError:
            raise TerminalError(f"Executable not found: {prog}")
        return {
            "command": command,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-MAX_OUTPUT:],
            "stderr": proc.stderr[-MAX_OUTPUT:],
            "ok": proc.returncode == 0,
        }

    # ── git convenience ────────────────────────────────────

    def git_status(self) -> Dict:
        return self.run("git status --porcelain=v1 -b")

    def git_diff_stat(self) -> Dict:
        return self.run("git diff --stat")

    def git_commit(self, message: str, add_all: bool = True,
                   paths: Optional[List[str]] = None) -> Dict:
        if paths:
            for p in paths:
                self.sec.resolve(p)  # sandbox check
            add = self.run("git add -- " + " ".join(shlex.quote(p) for p in paths))
        elif add_all:
            add = self.run("git add -A")
        else:
            add = {"ok": True}
        if not add.get("ok"):
            return add
        return self.run(f"git commit -m {shlex.quote(message)}")

    def git_push(self, remote: str = "origin", branch: Optional[str] = None) -> Dict:
        cmd = f"git push {shlex.quote(remote)}"
        if branch:
            cmd += f" {shlex.quote(branch)}"
        return self.run(cmd, timeout=180)

    def git_pull(self) -> Dict:
        return self.run("git pull --ff-only", timeout=180)

    def git_branch(self, name: Optional[str] = None) -> Dict:
        if name:
            return self.run(f"git checkout -b {shlex.quote(name)}")
        return self.run("git branch --show-current")
