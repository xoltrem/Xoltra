# Permission Bridge — Xoltra

Zero-Trust middleware between AI-generated nodes and the Local Agent.

## Files

| File | What it is |
|------|------------|
| `architecture.md` | System diagram + three-tier overview |
| `schemas.json` | JSON schemas for Node Manifest and App Permissions |
| `permission_bridge.py` | Core Python implementation — the interceptor |
| `security_guardrails.md` | 10 guardrails against prompt injection |

## Quick Start

```python
from permission_bridge import create_permission_bridge, NodeManifest, NodeAction, ApprovedApp

# Wire everything up
bridge, primitives = create_permission_bridge()

# Approve an app (user does this via UI)
bridge.registry.approve_app(ApprovedApp(
    app_id="local_filesystem",
    app_name="Local File System",
    allowed_actions=["READ", "WRITE"],
    allowed_scopes=["~/Downloads", "~/Documents"]
))

# Build a node manifest (AI generates this)
manifest = NodeManifest(
    node_id="abc-123",
    node_name="Read PDFs from Downloads",
    generated_by="ai",
    permissions=["read_only"],
    actions=[
        NodeAction("READ", "~/Downloads", "~/Downloads/*.pdf")
    ],
    safe_primitives_only=True,
    code="files = primitives.safe_list_files('~/Downloads', '*.pdf')"
)

# Check it — this is the interceptor
result = bridge.check_manifest(manifest)

if result.requires_consent:
    # Pause — show consent modal to user
    print("Blocked actions:", result.blocked_actions)
    # After user clicks Allow:
    bridge.grant_temporary_consent(manifest.node_id, result.blocked_actions)
    result = bridge.check_manifest(manifest)

if result.allowed:
    # Safe to execute
    files = primitives.safe_list_files("~/Downloads", "*.pdf")
    print(files)
```

## Install Dependencies

```bash
pip install requests
```

No other dependencies — uses Python stdlib only (subprocess, tempfile, json, os).
