# Xoltra Unity Client

Unity C# scripts for a visual/simulation client — separate from the web
`frontend/` (Next.js) and talks to `backend/` over its own channel
(`XoltraWebSocket.cs`).

| File | Purpose |
|---|---|
| `XoltraWebSocket.cs` | WebSocket connection to the backend |
| `XoltraSimManager.cs` | Top-level simulation lifecycle/state manager |
| `SimulationUI.cs` | In-scene UI for the simulation |
| `AgentPipelineView.cs` | Visualizes the Architect/Coder/Judge/Tester agent pipeline live |
| `WorkflowVisualizer.cs` | Renders workflow graphs (nodes/edges) in-scene |
| `NodeRenderer.cs` | Per-node visual representation |
| `DataManipulator.cs` | Data transform/manipulation helpers for the above |

Not part of the npm/pip build — open this folder as a Unity project
(or copy these scripts into an existing Unity project's `Assets/Scripts/`).
