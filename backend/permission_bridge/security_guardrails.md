# Xoltra Security Guardrails
# Preventing Prompt Injection in AI-Generated Nodes

## What is Prompt Injection here?
A user or malicious input tricks the AI into generating node code that bypasses
the Permission Bridge — e.g. a node that looks safe in its Manifest but contains
hidden code to delete files, exfiltrate data, or escalate permissions.

---

## Guardrail 1 — Safe Primitives Only (No Raw System Access)

AI-generated nodes are ONLY allowed to call functions from the SafePrimitives library.
They cannot import or call:

BANNED:
- os.system(), subprocess, shutil.rmtree(), os.remove()
- eval(), exec(), __import__(), importlib
- open() directly — must use Safe_File_Read / Safe_File_Write
- socket, requests directly — must use Safe_API_Call
- Any base64 decode + exec pattern

HOW IT'S ENFORCED:
- SandboxValidator runs a static pattern scan before any code is executed
- Banned patterns list is maintained in permission_bridge.py → SandboxValidator.BANNED_PATTERNS

---

## Guardrail 2 — Manifest Must Be Generated BEFORE Code

The AI must output the Node Manifest (declaring all intended actions) BEFORE
generating the execution code. This prevents the AI from hiding actions in code
that weren't declared in the manifest.

SYSTEM PROMPT RULE (add to all AI node generation prompts):
"You must output the Node Manifest JSON first, listing every file path, API endpoint,
and action type your code will use. Do not include any action in your code that is
not declared in the manifest."

---

## Guardrail 3 — Sandbox Dry-Run Before Real Execution

Every AI-generated node runs in a restricted subprocess with:
- DRY_RUN=1 environment variable injected
- No real network access
- 5 second timeout
- Captured stdout/stderr — any unexpected output fails validation

This catches obfuscated code that passes static analysis but fails at runtime.

---

## Guardrail 4 — Scope Pinning

The AI is not allowed to use wildcard or relative paths in manifests.

BANNED scope patterns:
- "/**" (recursive everything)
- "../" (path traversal)
- "~/" alone without a subdirectory (entire home directory)
- Regex patterns in paths

ALLOWED:
- "~/Documents/ProjectX"
- "~/Downloads/*.pdf"
- "api.spotify.com/playlists"

HOW IT'S ENFORCED:
- PermissionBridge._scope_allowed() validates scope against the approved green zone
- Scope pinning rules validated during manifest submission, before sandbox

---

## Guardrail 5 — No Cascading Node Generation

An AI node cannot generate or trigger other AI nodes. Node generation is a
human-initiated action only. This prevents:
- Self-replicating automation chains
- A node quietly expanding its own permissions by spawning child nodes

HOW IT'S ENFORCED:
- Orchestrator blocks any node whose code attempts to call the AI Synthesis Engine
- Banned pattern: any call to pipeline.run(), call_llm(), or the synthesis endpoint

---

## Guardrail 6 — API Key Isolation

API keys are NEVER passed directly to AI-generated code. The SafePrimitives
library resolves keys from environment variables at runtime.

BANNED in AI-generated code:
- Hardcoded strings that look like API keys (regex: [A-Za-z0-9_\-]{20,})
- Direct os.environ access
- Any attempt to read .env files

HOW IT'S ENFORCED:
- Static scan for hardcoded credential patterns
- Safe_API_Call resolves the key from the App Registry's api_key_ref internally

---

## Guardrail 7 — Human-Readable Audit Before Execution

For any node marked generated_by: "ai", the user sees a plain-English summary
of what the node will do before it runs:

Example consent modal text (auto-generated from manifest):
  "This AI node will:
   • READ files matching *.pdf from ~/Downloads
   • UPLOAD them to api.dropboxapi.com/2/files/upload
   Allow this?"

The user must click Allow — not just dismiss the modal.

---

## Guardrail 8 — One-Time vs Persistent Consent

Session consent (granted during a run) does NOT persist to the App Registry.
To make a permission permanent, the user must explicitly add it via the
Permissions Dashboard. This prevents a single "Allow" click from becoming
a permanent open door.

---

## Guardrail 9 — Rate Limiting on AI Node Generation

To prevent abuse (e.g. a node that loops and generates thousands of child actions):
- Max 10 AI-generated nodes per flow
- Max 50 actions per node manifest
- Max 5 API calls per node execution
- Cooldown: 2 seconds between node executions in the same flow

---

## Guardrail 10 — Prompt Template Hardening

The system prompt used to generate nodes must include these injections:

ALWAYS include in AI node generation system prompt:
```
You are generating automation node code for a Zero-Trust system.
Rules you cannot break:
1. Only use functions from the SafePrimitives library.
2. Declare every action in the Node Manifest before writing any code.
3. Never use eval(), exec(), os.system(), subprocess, or raw open().
4. Never access environment variables or config files directly.
5. Never generate code that calls the AI or spawns other nodes.
6. If you cannot complete the task within these constraints, say so — do not attempt workarounds.
```

If the AI responds with "I cannot do this within the constraints" — that is
the CORRECT and SAFE response. Never override or work around it.
