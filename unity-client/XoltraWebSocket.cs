// XoltraWebSocket.cs
// Connects to unity_bridge.py WebSocket server.
// Receives SimCommands as JSON strings and raises OnCommandReceived.
// Sends Unity events back to Python.
//
// Setup:
//   1. Install NativeWebSocket:  Window → Package Manager → + → Add from git URL
//      https://github.com/endel/NativeWebSocket.git#upm
//   2. Attach this script to a persistent GameObject (e.g. "XoltraSimManager")
//   3. Set BridgeUrl in the Inspector (default: ws://localhost:5002)

using System;
using System.Collections;
using System.Text;
using UnityEngine;
using NativeWebSocket;

namespace Xoltra.Simulation
{
    public class XoltraWebSocket : MonoBehaviour
    {
        // ── Inspector ─────────────────────────────────────────────────────────
        [Header("Bridge Connection")]
        [Tooltip("WebSocket URL of unity_bridge.py")]
        public string BridgeUrl = "ws://localhost:5002";

        [Tooltip("Seconds between reconnect attempts")]
        public float ReconnectDelay = 3f;

        // ── Events ────────────────────────────────────────────────────────────
        /// Fires on the Unity main thread with the raw JSON command string.
        public event Action<string> OnCommandReceived;

        /// Fires when the connection state changes.
        public event Action<bool> OnConnectionChanged;

        // ── State ─────────────────────────────────────────────────────────────
        public bool IsConnected => _ws != null && _ws.State == WebSocketState.Open;

        private WebSocket _ws;
        private bool      _reconnect = true;
        private Coroutine _reconnectCoroutine;

        // ═════════════════════════════════════════════════════════════════════
        // LIFECYCLE
        // ═════════════════════════════════════════════════════════════════════

        private void Start()
        {
            _reconnect = true;
            ConnectAsync();
        }

        private void Update()
        {
            // NativeWebSocket requires DispatchMessageQueue on the main thread.
#if !UNITY_WEBGL || UNITY_EDITOR
            _ws?.DispatchMessageQueue();
#endif
        }

        private void OnDestroy()
        {
            _reconnect = false;
            _ws?.Close();
        }

        // ═════════════════════════════════════════════════════════════════════
        // CONNECTION
        // ═════════════════════════════════════════════════════════════════════

        private async void ConnectAsync()
        {
            _ws = new WebSocket(BridgeUrl);

            _ws.OnOpen += () =>
            {
                Debug.Log("[XoltraWS] Connected to bridge");
                OnConnectionChanged?.Invoke(true);
                // Send scene-ready event
                SendEvent("scene_ready", "{}");
            };

            _ws.OnClose += (code) =>
            {
                Debug.Log($"[XoltraWS] Disconnected ({code})");
                OnConnectionChanged?.Invoke(false);
                if (_reconnect && _reconnectCoroutine == null)
                    _reconnectCoroutine = StartCoroutine(ReconnectLoop());
            };

            _ws.OnError += (err) =>
            {
                Debug.LogWarning($"[XoltraWS] Error: {err}");
            };

            _ws.OnMessage += (bytes) =>
            {
                string json = Encoding.UTF8.GetString(bytes);
                OnCommandReceived?.Invoke(json);
            };

            await _ws.Connect();
        }

        private IEnumerator ReconnectLoop()
        {
            yield return new WaitForSeconds(ReconnectDelay);
            _reconnectCoroutine = null;
            if (_reconnect && !IsConnected)
            {
                Debug.Log("[XoltraWS] Reconnecting…");
                ConnectAsync();
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        // SEND — Unity → Python
        // ═════════════════════════════════════════════════════════════════════

        /// Send a JSON event payload to Python.
        public async void SendEvent(string eventType, string payloadJson)
        {
            if (!IsConnected) return;
            string msg = $"{{\"type\":\"{eventType}\",\"payload\":{payloadJson}}}";
            await _ws.SendText(msg);
        }

        /// Convenience: send a node-clicked event.
        public void SendNodeClicked(string nodeId, string nodeType)
        {
            SendEvent("node_clicked",
                $"{{\"node_id\":\"{nodeId}\",\"node_type\":\"{nodeType}\"}}");
        }

        /// Convenience: send a step-clicked event.
        public void SendStepClicked(int phaseIndex, int stepIndex)
        {
            SendEvent("step_clicked",
                $"{{\"phase_index\":{phaseIndex},\"step_index\":{stepIndex}}}");
        }

        /// Convenience: send a user field-edit event.
        public void SendFieldEdit(string objId, string fieldPath, string newValue)
        {
            SendEvent("user_edit_field",
                $"{{\"obj_id\":\"{objId}\",\"field_path\":\"{fieldPath}\"," +
                $"\"new_value\":\"{EscapeJson(newValue)}\"}}");
        }

        private static string EscapeJson(string s) =>
            s?.Replace("\\", "\\\\").Replace("\"", "\\\"") ?? "";
    }
}
