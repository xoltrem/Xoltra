# Xoltra Permission Bridge — Architecture

## System Data Flow

```mermaid
flowchart TD
    User(["👤 User"])
    UI["Orchestrator UI\n(React + React Flow)"]
    AIGen["AI Synthesis Engine\n(LLM Node Generator)"]
    Manifest["Node Manifest\n(JSON Schema)"]
    Bridge["Permission Bridge\n(Interceptor)"]
    Registry["App Registry\n(Approved Apps + Scopes)"]
    Consent["JIT Consent Modal\n(UI Pause Gate)"]
    Sandbox["Shadow Sandbox\n(Docker / subprocess)"]
    Agent["Local Agent\n(Data Plane)"]
    AuditLog["Audit Log\n(Human-Readable)"]
    OS["OS / External APIs"]

    User -->|"Describes task in natural language"| UI
    UI -->|"Sends prompt to AI"| AIGen
    AIGen -->|"Generates Node + Manifest"| Manifest
    Manifest -->|"Node submitted to flow"| Bridge

    Bridge -->|"Check: is app approved?"| Registry
    Registry -->|"Approved ✅"| Bridge
    Registry -->|"Not approved ❌"| Consent
    Consent -->|"User allows"| Bridge
    Consent -->|"User denies"| UI

    Bridge -->|"Validate generated code"| Sandbox
    Sandbox -->|"Safe ✅"| Agent
    Sandbox -->|"Unsafe ❌ — blocked"| AuditLog

    Agent -->|"Execute action"| OS
    Agent -->|"Log every action"| AuditLog
    AuditLog -->|"Shown to user"| UI
```

## Three-Tier Summary

| Tier | Name | Responsibility |
|------|------|----------------|
| 1 | Orchestrator (Control Plane) | UI, flow state, node connections, triggers |
| 2 | Permission Bridge (Security Plane) | Manifest checks, JIT consent, sandbox validation |
| 3 | Local Agent (Data Plane) | OS-level execution, API calls, audit logging |

## Key Security Principles

- **Zero Trust** — no node is trusted by default, every action is checked
- **Manifest-First** — nodes must declare what they need before they can run
- **JIT Consent** — permission is granted per-action, not per-session
- **Sandbox Validation** — AI-generated code is tested in isolation before touching real data
- **Audit Everything** — every action is logged in plain English for the user
