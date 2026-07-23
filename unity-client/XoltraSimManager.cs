// XoltraSimManager.cs
// Main controller. Parses incoming SimCommands and delegates to
// NodeRenderer, WorkflowVisualizer, AgentPipelineView, DataManipulator.
//
// Attach to a single persistent GameObject: "XoltraSimManager"
// Drag the other renderer GameObjects into the Inspector slots.

using System.Collections.Generic;
using UnityEngine;
using Newtonsoft.Json;       // Install via: Window → Package Manager → Newtonsoft Json

namespace Xoltra.Simulation
{
    public class XoltraSimManager : MonoBehaviour
    {
        // ── Inspector slots ───────────────────────────────────────────────────
        [Header("Sub-systems")]
        public NodeRenderer          NodeRenderer;
        public WorkflowVisualizer    WorkflowVisualizer;
        public AgentPipelineView     AgentPipelineView;
        public DataManipulator       DataManipulator;
        public SimulationUI          SimUI;

        [Header("WebSocket")]
        public XoltraWebSocket WebSocket;

        // ═════════════════════════════════════════════════════════════════════
        // LIFECYCLE
        // ═════════════════════════════════════════════════════════════════════

        private void Awake()
        {
            if (WebSocket == null)
                WebSocket = GetComponent<XoltraWebSocket>();
        }

        private void OnEnable()
        {
            WebSocket.OnCommandReceived  += HandleCommand;
            WebSocket.OnConnectionChanged += HandleConnectionChanged;
        }

        private void OnDisable()
        {
            WebSocket.OnCommandReceived  -= HandleCommand;
            WebSocket.OnConnectionChanged -= HandleConnectionChanged;
        }

        private void HandleConnectionChanged(bool connected)
        {
            SimUI?.SetConnectionBadge(connected);
            Debug.Log($"[SimManager] Bridge {(connected ? "connected" : "disconnected")}");
        }

        // ═════════════════════════════════════════════════════════════════════
        // COMMAND DISPATCH
        // ═════════════════════════════════════════════════════════════════════

        private void HandleCommand(string json)
        {
            SimCommand cmd;
            try
            {
                cmd = JsonConvert.DeserializeObject<SimCommand>(json);
            }
            catch (System.Exception e)
            {
                Debug.LogWarning($"[SimManager] Parse error: {e.Message}\n{json}");
                return;
            }

            if (cmd == null || string.IsNullOrEmpty(cmd.Type))
                return;

            switch (cmd.Type)
            {
                // ── Scene control ─────────────────────────────────────────
                case "clear_scene":
                    ClearAll();
                    break;

                case "set_camera":
                    HandleSetCamera(cmd.Payload);
                    break;

                // ── Node graph ────────────────────────────────────────────
                case "render_node":
                    NodeRenderer?.RenderNode(cmd.Payload);
                    break;

                case "update_node":
                    NodeRenderer?.UpdateNode(cmd.Payload);
                    break;

                case "remove_node":
                    NodeRenderer?.RemoveNode(GetStr(cmd.Payload, "node_id"));
                    break;

                case "render_edge":
                    NodeRenderer?.RenderEdge(cmd.Payload);
                    break;

                case "highlight_node":
                    NodeRenderer?.HighlightNode(
                        GetStr(cmd.Payload, "node_id"),
                        GetStr(cmd.Payload, "color"),
                        GetBool(cmd.Payload, "pulse")
                    );
                    break;

                case "highlight_path":
                    NodeRenderer?.HighlightPath(cmd.Payload);
                    break;

                // ── Workflow ──────────────────────────────────────────────
                case "render_workflow":
                    WorkflowVisualizer?.RenderWorkflow(cmd.Payload);
                    break;

                case "advance_phase":
                    WorkflowVisualizer?.AdvancePhase(GetInt(cmd.Payload, "phase_index"));
                    break;

                case "complete_step":
                    WorkflowVisualizer?.CompleteStep(
                        GetInt(cmd.Payload, "phase_index"),
                        GetInt(cmd.Payload, "step_index")
                    );
                    break;

                case "set_phase_status":
                    WorkflowVisualizer?.SetPhaseStatus(
                        GetInt(cmd.Payload, "phase_index"),
                        GetStr(cmd.Payload, "status")
                    );
                    break;

                // ── Agent pipeline ────────────────────────────────────────
                case "render_pipeline":
                    AgentPipelineView?.RenderPipeline(cmd.Payload);
                    break;

                case "activate_agent":
                    AgentPipelineView?.ActivateAgent(GetStr(cmd.Payload, "agent_name"));
                    break;

                case "complete_agent":
                    AgentPipelineView?.CompleteAgent(
                        GetStr(cmd.Payload, "agent_name"),
                        GetStr(cmd.Payload, "output_preview")
                    );
                    break;

                case "agent_error":
                    AgentPipelineView?.ErrorAgent(GetStr(cmd.Payload, "agent_name"),
                                                  GetStr(cmd.Payload, "error"));
                    break;

                case "show_agent_output":
                    AgentPipelineView?.ShowOutput(cmd.Payload);
                    break;

                // ── Data manipulation ─────────────────────────────────────
                case "load_data_object":
                    DataManipulator?.LoadObject(cmd.Payload);
                    break;

                case "mutate_field":
                    DataManipulator?.MutateField(cmd.Payload);
                    break;

                case "animate_transform":
                    DataManipulator?.AnimateTransform(cmd.Payload);
                    break;

                case "show_diff":
                    DataManipulator?.ShowDiff(cmd.Payload);
                    break;

                // ── UI ────────────────────────────────────────────────────
                case "show_toast":
                    SimUI?.ShowToast(
                        GetStr(cmd.Payload, "message"),
                        GetStr(cmd.Payload, "level")
                    );
                    break;

                case "show_modal":
                    SimUI?.ShowModal(cmd.Payload);
                    break;

                case "update_status_bar":
                    SimUI?.UpdateStatusBar(
                        GetStr(cmd.Payload, "text"),
                        GetFloat(cmd.Payload, "progress")
                    );
                    break;

                // ── Handshake (from bridge on connect) ────────────────────
                case "handshake":
                    Debug.Log("[SimManager] Handshake received — bridge v" +
                              GetStr(cmd.Payload, "version"));
                    break;

                default:
                    Debug.LogWarning($"[SimManager] Unknown command type: {cmd.Type}");
                    break;
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        // CLEAR
        // ═════════════════════════════════════════════════════════════════════

        private void ClearAll()
        {
            NodeRenderer?.ClearAll();
            WorkflowVisualizer?.ClearAll();
            AgentPipelineView?.ClearAll();
            DataManipulator?.ClearAll();
        }

        // ═════════════════════════════════════════════════════════════════════
        // CAMERA
        // ═════════════════════════════════════════════════════════════════════

        private void HandleSetCamera(Dictionary<string, object> p)
        {
            if (Camera.main == null) return;
            if (p.ContainsKey("x") && p.ContainsKey("y") && p.ContainsKey("z"))
            {
                Camera.main.transform.position = new Vector3(
                    GetFloat(p, "x"), GetFloat(p, "y"), GetFloat(p, "z")
                );
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        // PAYLOAD HELPERS
        // ═════════════════════════════════════════════════════════════════════

        public static string GetStr(Dictionary<string, object> d, string key, string def = "")
            => d.TryGetValue(key, out var v) ? v?.ToString() ?? def : def;

        public static bool GetBool(Dictionary<string, object> d, string key, bool def = false)
            => d.TryGetValue(key, out var v) && v is bool b ? b : def;

        public static int GetInt(Dictionary<string, object> d, string key, int def = 0)
        {
            if (!d.TryGetValue(key, out var v)) return def;
            return v is long l ? (int)l : (v is int i ? i : def);
        }

        public static float GetFloat(Dictionary<string, object> d, string key, float def = 0f)
        {
            if (!d.TryGetValue(key, out var v)) return def;
            if (v is double db) return (float)db;
            if (v is float f)   return f;
            if (v is long l)    return (float)l;
            return def;
        }
    }

    // ── Wire-format model ─────────────────────────────────────────────────────
    [System.Serializable]
    public class SimCommand
    {
        [JsonProperty("type")]    public string                      Type;
        [JsonProperty("id")]      public string                      Id;
        [JsonProperty("payload")] public Dictionary<string, object>  Payload
            = new Dictionary<string, object>();
    }
}
