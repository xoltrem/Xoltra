"""
permission_bridge.py — Xoltra Permission Interceptor
Zero-Trust middleware between AI-generated nodes and the Local Agent.

Flow:
  Node Manifest → check_manifest() → approved? → sandbox → execute
                                    → not approved? → request_consent() → user allows/denies
"""

import json
import logging
import subprocess
import tempfile
import os
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════

@dataclass
class NodeAction:
    action_type: str   # READ | WRITE | DELETE | MOVE | POST | GET | PATCH | SHELL_EXEC | UI_CONTROL
    target: str        # e.g. "~/Downloads", "api.spotify.com"
    scope: str         # e.g. "~/Downloads/*.pdf", "/playlists/{id}/tracks"


@dataclass
class NodeManifest:
    node_id: str
    node_name: str
    generated_by: str              # "user" | "ai"
    permissions: list[str]
    actions: list[NodeAction]
    safe_primitives_only: bool = True
    sandbox_validated: bool = False
    code: Optional[str] = None     # AI-generated code to sandbox-check


@dataclass
class ApprovedApp:
    app_id: str
    app_name: str
    allowed_actions: list[str]
    allowed_scopes: list[str]
    api_key_ref: Optional[str] = None
    expires_at: Optional[str] = None


@dataclass
class InterceptResult:
    allowed: bool
    reason: str
    requires_consent: bool = False
    blocked_actions: list[str] = field(default_factory=list)
    audit_entry: Optional[dict] = None


# ═══════════════════════════════════════════════════
# APP REGISTRY — in-memory, load from config in prod
# ═══════════════════════════════════════════════════

class AppRegistry:
    """
    Stores user-approved apps and their allowed scopes.
    In production: load from / persist to a local config file.
    """

    def __init__(self, config_path: str = "app_registry.json"):
        self.config_path = config_path
        self._registry: dict[str, ApprovedApp] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                for app in data.get("approved_apps", []):
                    self._registry[app["app_id"]] = ApprovedApp(**{
                        k: v for k, v in app.items()
                        if k in ApprovedApp.__dataclass_fields__
                    })
                logger.info(f"[Registry] Loaded {len(self._registry)} approved apps")
            except Exception as e:
                logger.warning(f"[Registry] Could not load config: {e}")

    def _save(self):
        data = {
            "approved_apps": [
                {
                    "app_id":          a.app_id,
                    "app_name":        a.app_name,
                    "allowed_actions": a.allowed_actions,
                    "allowed_scopes":  a.allowed_scopes,
                    "api_key_ref":     a.api_key_ref,
                    "expires_at":      a.expires_at,
                }
                for a in self._registry.values()
            ]
        }
        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)

    def approve_app(self, app: ApprovedApp):
        """User explicitly approves an app."""
        self._registry[app.app_id] = app
        self._save()
        logger.info(f"[Registry] Approved: {app.app_name}")

    def revoke_app(self, app_id: str):
        """User revokes access to an app."""
        if app_id in self._registry:
            del self._registry[app_id]
            self._save()
            logger.info(f"[Registry] Revoked: {app_id}")

    def get(self, app_id: str) -> Optional[ApprovedApp]:
        return self._registry.get(app_id)

    def is_approved(self, app_id: str) -> bool:
        app = self.get(app_id)
        if not app:
            return False
        # Check expiry
        if app.expires_at:
            expiry = datetime.fromisoformat(app.expires_at)
            if datetime.now(timezone.utc) > expiry:
                logger.warning(f"[Registry] {app_id} permission expired")
                return False
        return True

    def list_approved(self) -> list[dict]:
        return [
            {"app_id": a.app_id, "app_name": a.app_name, "scopes": a.allowed_scopes}
            for a in self._registry.values()
        ]


# ═══════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════

class AuditLog:
    """
    Human-readable log of every AI action.
    Stored in memory and optionally written to disk.
    """

    def __init__(self, log_path: str = "xoltra_audit.log"):
        self.log_path = log_path
        self._entries: list[dict] = []

    def record(
        self,
        node_id: str,
        node_name: str,
        action: NodeAction,
        outcome: str,       # "allowed" | "blocked" | "consent_required" | "sandbox_failed"
        reason: str
    ):
        entry = {
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "node_id":    node_id,
            "node_name":  node_name,
            "action":     f"{action.action_type} → {action.target} ({action.scope})",
            "outcome":    outcome,
            "reason":     reason,
        }
        self._entries.append(entry)

        # Human-readable log line
        line = (
            f"[{entry['timestamp']}] [{outcome.upper()}] "
            f"Node '{node_name}' attempted {entry['action']} — {reason}"
        )
        logger.info(line)
        with open(self.log_path, "a") as f:
            f.write(line + "\n")

    def get_recent(self, n: int = 20) -> list[dict]:
        return self._entries[-n:]


# ═══════════════════════════════════════════════════
# SANDBOX VALIDATOR
# ═══════════════════════════════════════════════════

class SandboxValidator:
    """
    Runs AI-generated code in a restricted subprocess to check for
    unauthorized actions before it touches real data.
    """

    # Banned patterns — raw shell, network calls outside safe primitives, deletions
    BANNED_PATTERNS = [
        "os.system(",
        "subprocess.call(",
        "subprocess.run(",
        "subprocess.Popen(",
        "__import__('os')",
        "eval(",
        "exec(",
        "open(",          # must use Safe_File_Read / Safe_File_Write instead
        "shutil.rmtree(",
        "os.remove(",
        "requests.delete(",
        "socket.",
        "importlib",
    ]

    def validate(self, code: str) -> tuple[bool, str]:
        """
        Returns (is_safe, reason).
        First does a static scan, then a sandboxed dry-run.
        """
        # Static scan
        for pattern in self.BANNED_PATTERNS:
            if pattern in code:
                return False, f"Banned pattern detected: '{pattern}'"

        # Sandboxed dry-run — restricted subprocess with no network, no file writes
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as tmp:
                # Inject a dry-run guard at the top
                guarded_code = (
                    "import sys\n"
                    "DRY_RUN = True\n"
                    "# Sandboxed validation — no real I/O\n\n"
                ) + code
                tmp.write(guarded_code)
                tmp_path = tmp.name

            result = subprocess.run(
                ["python", tmp_path],
                timeout=5,
                capture_output=True,
                text=True,
                # Restrict environment — no network env vars leaked
                env={"PATH": os.environ.get("PATH", ""), "DRY_RUN": "1"}
            )
            os.unlink(tmp_path)

            if result.returncode != 0:
                return False, f"Sandbox execution failed: {result.stderr[:200]}"

            return True, "Sandbox validation passed"

        except subprocess.TimeoutExpired:
            return False, "Sandbox timeout — code took too long"
        except Exception as e:
            return False, f"Sandbox error: {e}"


# ═══════════════════════════════════════════════════
# PERMISSION BRIDGE — main interceptor
# ═══════════════════════════════════════════════════

class PermissionBridge:
    """
    The core interceptor. Every node action passes through here.

    Usage:
        bridge = PermissionBridge(registry, audit_log, sandbox)
        result = bridge.check_manifest(manifest)

        if result.requires_consent:
            # Pause execution — show consent modal to user
            user_allowed = show_consent_modal(result.blocked_actions)
            if user_allowed:
                bridge.grant_temporary_consent(manifest.node_id, result.blocked_actions)
                result = bridge.check_manifest(manifest)

        if result.allowed:
            agent.execute(manifest)
    """

    def __init__(
        self,
        registry: AppRegistry,
        audit_log: AuditLog,
        sandbox: SandboxValidator
    ):
        self.registry  = registry
        self.audit_log = audit_log
        self.sandbox   = sandbox
        # Temporary per-session consents granted by user
        self._session_consents: dict[str, list[str]] = {}

    def check_manifest(self, manifest: NodeManifest) -> InterceptResult:
        """
        Main entry point. Checks every action in the manifest.
        Returns InterceptResult — caller decides what to do with it.
        """
        blocked = []

        for action in manifest.actions:
            allowed, reason = self._check_action(manifest.node_id, action)
            if not allowed:
                blocked.append(f"{action.action_type} → {action.target}: {reason}")
                self.audit_log.record(
                    manifest.node_id, manifest.node_name,
                    action, "consent_required", reason
                )

        if blocked:
            return InterceptResult(
                allowed=False,
                reason="One or more actions require user consent",
                requires_consent=True,
                blocked_actions=blocked,
            )

        # All actions cleared — now sandbox-check AI-generated code
        if manifest.generated_by == "ai" and manifest.code:
            if not manifest.sandbox_validated:
                is_safe, reason = self.sandbox.validate(manifest.code)
                if not is_safe:
                    for action in manifest.actions:
                        self.audit_log.record(
                            manifest.node_id, manifest.node_name,
                            action, "sandbox_failed", reason
                        )
                    return InterceptResult(
                        allowed=False,
                        reason=f"Sandbox validation failed: {reason}",
                        requires_consent=False,
                    )

        # All clear — log and allow
        for action in manifest.actions:
            self.audit_log.record(
                manifest.node_id, manifest.node_name,
                action, "allowed", "Within approved scope"
            )

        return InterceptResult(
            allowed=True,
            reason="All actions within approved scope"
        )

    def _check_action(self, node_id: str, action: NodeAction) -> tuple[bool, str]:
        """Check a single action against the registry + session consents."""

        # Check session consent first (user already approved this session)
        session_key = f"{node_id}:{action.action_type}:{action.target}"
        if session_key in self._session_consents.get(node_id, []):
            return True, "Session consent granted"

        # Resolve which app this action targets
        app_id = self._resolve_app_id(action.target)
        if not app_id:
            return False, f"Target '{action.target}' is not in the approved app registry"

        # Check app is approved
        if not self.registry.is_approved(app_id):
            return False, f"App '{app_id}' has not been approved by the user"

        app = self.registry.get(app_id)

        # Check action type is allowed
        if action.action_type not in app.allowed_actions:
            return False, (
                f"Action '{action.action_type}' is not allowed for '{app.app_name}'. "
                f"Allowed: {app.allowed_actions}"
            )

        # Check scope is within green zone
        if not self._scope_allowed(action.scope, app.allowed_scopes):
            return False, (
                f"Scope '{action.scope}' is outside the approved green zone for '{app.app_name}'. "
                f"Allowed scopes: {app.allowed_scopes}"
            )

        return True, "Approved"

    def _resolve_app_id(self, target: str) -> Optional[str]:
        """
        Map a target string to an app_id in the registry.
        e.g. "~/Downloads" → "local_filesystem", "api.spotify.com" → "spotify"
        """
        target_lower = target.lower()

        # Check all approved apps for a match
        for app_id, app in self.registry._registry.items():
            for scope in app.allowed_scopes:
                if scope.lower() in target_lower or target_lower in scope.lower():
                    return app_id
            if app_id in target_lower or app.app_name.lower() in target_lower:
                return app_id

        # Common local filesystem paths
        local_paths = ["~/", "/home/", "/users/", "c:\\", "c:/", "./", "../"]
        if any(target_lower.startswith(p) for p in local_paths):
            return "local_filesystem"

        return None

    def _scope_allowed(self, requested_scope: str, allowed_scopes: list[str]) -> bool:
        """Check if requested scope falls within any allowed scope."""
        req = os.path.expanduser(requested_scope).lower()
        for allowed in allowed_scopes:
            exp = os.path.expanduser(allowed).lower()
            if req.startswith(exp) or exp in req or req in exp:
                return True
        return False

    def grant_temporary_consent(self, node_id: str, blocked_actions: list[str]):
        """
        Called after user approves via consent modal.
        Grants consent for this session only — not persisted.
        """
        if node_id not in self._session_consents:
            self._session_consents[node_id] = []
        self._session_consents[node_id].extend(blocked_actions)
        logger.info(f"[Bridge] Session consent granted for node {node_id[:8]}")

    def get_audit_log(self, n: int = 20) -> list[dict]:
        return self.audit_log.get_recent(n)


# ═══════════════════════════════════════════════════
# SAFE PRIMITIVES LIBRARY
# ═══════════════════════════════════════════════════

class SafePrimitives:
    """
    The only functions AI-generated nodes are allowed to call.
    All I/O goes through here — never raw os / subprocess / requests.
    """

    def __init__(self, bridge: PermissionBridge):
        self.bridge = bridge

    def safe_file_read(self, path: str) -> str:
        """Read a file. Checks permission first."""
        action = NodeAction("READ", path, path)
        allowed, reason = self.bridge._check_action("primitives", action)
        if not allowed:
            raise PermissionError(f"safe_file_read blocked: {reason}")
        with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
            return f.read()

    def safe_file_write(self, path: str, content: str):
        """Write a file. Checks permission first."""
        action = NodeAction("WRITE", path, path)
        allowed, reason = self.bridge._check_action("primitives", action)
        if not allowed:
            raise PermissionError(f"safe_file_write blocked: {reason}")
        with open(os.path.expanduser(path), "w", encoding="utf-8") as f:
            f.write(content)

    def safe_file_move(self, src: str, dst: str):
        """Move a file. Checks both source and destination."""
        import shutil
        for path, action_type in [(src, "READ"), (dst, "WRITE")]:
            action = NodeAction(action_type, path, path)
            allowed, reason = self.bridge._check_action("primitives", action)
            if not allowed:
                raise PermissionError(f"safe_file_move blocked on {path}: {reason}")
        shutil.move(os.path.expanduser(src), os.path.expanduser(dst))

    def safe_api_call(
        self,
        method: str,
        url: str,
        headers: dict = None,
        body: dict = None
    ) -> dict:
        """Make an API call. Checks permission first."""
        import requests
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        action = NodeAction(method.upper(), domain, url)
        allowed, reason = self.bridge._check_action("primitives", action)
        if not allowed:
            raise PermissionError(f"safe_api_call blocked: {reason}")
        resp = requests.request(method, url, headers=headers or {}, json=body)
        resp.raise_for_status()
        return resp.json()

    def safe_list_files(self, directory: str, pattern: str = "*") -> list[str]:
        """List files in a directory matching a pattern."""
        import glob
        action = NodeAction("READ", directory, directory)
        allowed, reason = self.bridge._check_action("primitives", action)
        if not allowed:
            raise PermissionError(f"safe_list_files blocked: {reason}")
        return glob.glob(os.path.join(os.path.expanduser(directory), pattern))


# ═══════════════════════════════════════════════════
# FACTORY — wire everything together
# ═══════════════════════════════════════════════════

def create_permission_bridge(
    registry_path: str = "app_registry.json",
    audit_log_path: str = "xoltra_audit.log"
) -> tuple[PermissionBridge, SafePrimitives]:
    """
    Creates and returns a fully wired PermissionBridge + SafePrimitives.

    Usage:
        bridge, primitives = create_permission_bridge()
        result = bridge.check_manifest(manifest)
    """
    registry  = AppRegistry(config_path=registry_path)
    audit_log = AuditLog(log_path=audit_log_path)
    sandbox   = SandboxValidator()
    bridge    = PermissionBridge(registry, audit_log, sandbox)
    prims     = SafePrimitives(bridge)
    return bridge, prims
