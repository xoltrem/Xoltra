// AgentPipelineView.cs
// Renders the 14-agent pipeline as a horizontal chain.
// Each agent node animates through: pending → active (pulsing) → done.

using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using TMPro;

namespace Xoltra.Simulation
{
    public class AgentPipelineView : MonoBehaviour
    {
        // ── Inspector ─────────────────────────────────────────────────────────
        public GameObject AgentNodePrefab;
        public float      NodeSpacing   = 2.8f;
        public float      SpawnDuration = 0.2f;

        // ── Colors ────────────────────────────────────────────────────────────
        private static readonly Color ColPending = new Color(0.180f, 0.180f, 0.220f);
        private static readonly Color ColActive  = new Color(0.957f, 0.651f, 0.137f);
        private static readonly Color ColDone    = new Color(0.133f, 0.722f, 0.647f);
        private static readonly Color ColError   = new Color(0.937f, 0.341f, 0.270f);

        // ── Runtime ───────────────────────────────────────────────────────────
        private readonly Dictionary<string, GameObject> _agentNodes = new();
        private readonly Dictionary<string, Coroutine>  _pulseJobs  = new();
        private GameObject _tierLabel;

        // ═════════════════════════════════════════════════════════════════════
        // RENDER PIPELINE
        // ═════════════════════════════════════════════════════════════════════

        public void RenderPipeline(Dictionary<string, object> p)
        {
            ClearAll();

            var raw    = p.TryGetValue("agents", out var a) ? a as List<object> : null;
            string tier = XoltraSimManager.GetStr(p, "tier", "medium");
            if (raw == null) return;

            float totalW = (raw.Count - 1) * NodeSpacing;

            for (int i = 0; i < raw.Count; i++)
            {
                string name = raw[i]?.ToString() ?? $"agent_{i}";
                float  x    = i * NodeSpacing - totalW / 2f;

                var go  = Instantiate(AgentNodePrefab,
                          new Vector3(x, 0f, 0f), Quaternion.identity, transform);
                go.name = $"Agent_{name}";

                SetText(go, "NameText",  FormatAgentName(name));
                SetText(go, "StateText", "pending");
                SetMeshColor(go, ColPending);

                go.transform.localScale = Vector3.zero;
                StartCoroutine(PopIn(go.transform, SpawnDuration + i * 0.04f));

                _agentNodes[name] = go;

                // Arrow between agents
                if (i < raw.Count - 1)
                    SpawnArrow(new Vector3(x + NodeSpacing * 0.5f, 0f, 0f));
            }

            // Tier badge
            _tierLabel = SpawnLabel($"[ {tier.ToUpper()} TIER ]",
                new Vector3(0f, 1.8f, 0f), new Color(0.957f, 0.651f, 0.137f));
        }

        // ═════════════════════════════════════════════════════════════════════
        // STATE TRANSITIONS
        // ═════════════════════════════════════════════════════════════════════

        public void ActivateAgent(string name)
        {
            if (!_agentNodes.TryGetValue(name, out var go)) return;
            SetMeshColor(go, ColActive);
            SetText(go, "StateText", "running…");

            if (_pulseJobs.TryGetValue(name, out var prev)) StopCoroutine(prev);
            _pulseJobs[name] = StartCoroutine(Pulse(go.transform));
        }

        public void CompleteAgent(string name, string outputPreview)
        {
            if (!_agentNodes.TryGetValue(name, out var go)) return;

            if (_pulseJobs.TryGetValue(name, out var job)) StopCoroutine(job);
            _pulseJobs.Remove(name);
            go.transform.localScale = Vector3.one;

            SetMeshColor(go, ColDone);
            SetText(go, "StateText", "done");

            if (!string.IsNullOrEmpty(outputPreview))
                SetText(go, "OutputText", Truncate(outputPreview, 60));
        }

        public void ErrorAgent(string name, string error)
        {
            if (!_agentNodes.TryGetValue(name, out var go)) return;
            if (_pulseJobs.TryGetValue(name, out var job)) StopCoroutine(job);
            _pulseJobs.Remove(name);
            SetMeshColor(go, ColError);
            SetText(go, "StateText", "error");
            SetText(go, "OutputText", Truncate(error, 60));
        }

        public void ShowOutput(Dictionary<string, object> p)
        {
            string name    = XoltraSimManager.GetStr(p, "agent_name");
            string preview = XoltraSimManager.GetStr(p, "output_preview");
            if (_agentNodes.TryGetValue(name, out var go))
                SetText(go, "OutputText", Truncate(preview, 80));
        }

        // ═════════════════════════════════════════════════════════════════════
        // CLEAR
        // ═════════════════════════════════════════════════════════════════════

        public void ClearAll()
        {
            StopAllCoroutines();
            foreach (var go in _agentNodes.Values) Destroy(go);
            _agentNodes.Clear();
            _pulseJobs.Clear();

            if (_tierLabel) Destroy(_tierLabel);

            foreach (Transform child in transform)
                Destroy(child.gameObject);
        }

        // ═════════════════════════════════════════════════════════════════════
        // HELPERS
        // ═════════════════════════════════════════════════════════════════════

        private IEnumerator Pulse(Transform t)
        {
            while (true)
            {
                float e = 0f;
                while (e < 0.5f) { e += Time.deltaTime; t.localScale = Vector3.one * (1f + 0.12f * Mathf.Sin(e / 0.5f * Mathf.PI)); yield return null; }
                yield return new WaitForSeconds(0.1f);
            }
        }

        private IEnumerator PopIn(Transform t, float delay)
        {
            yield return new WaitForSeconds(delay);
            float e = 0f;
            while (e < SpawnDuration) { e += Time.deltaTime; t.localScale = Vector3.one * (e / SpawnDuration); yield return null; }
            t.localScale = Vector3.one;
        }

        private void SpawnArrow(Vector3 pos)
        {
            var go  = new GameObject("Arrow");
            go.transform.parent   = transform;
            go.transform.position = pos;
            var tmp = go.AddComponent<TextMeshPro>();
            tmp.text      = "→";
            tmp.color     = new Color(0.420f, 0.420f, 0.470f);
            tmp.fontSize  = 4f;
            tmp.alignment = TextAlignmentOptions.Center;
        }

        private GameObject SpawnLabel(string text, Vector3 pos, Color color)
        {
            var go  = new GameObject("Label_" + text);
            go.transform.parent    = transform;
            go.transform.position  = pos;
            var tmp = go.AddComponent<TextMeshPro>();
            tmp.text      = text;
            tmp.color     = color;
            tmp.fontSize  = 3f;
            tmp.alignment = TextAlignmentOptions.Center;
            return go;
        }

        private static void SetText(GameObject go, string childName, string text)
        {
            var t = go.transform.Find(childName);
            if (t == null) return;
            var tmp = t.GetComponent<TextMeshPro>();
            if (tmp != null) tmp.text = text;
        }

        private static void SetMeshColor(GameObject go, Color c)
        {
            var mr = go.GetComponentInChildren<MeshRenderer>();
            if (mr != null) mr.material.color = c;
        }

        private static string FormatAgentName(string s) =>
            System.Globalization.CultureInfo.CurrentCulture.TextInfo
                  .ToTitleCase(s.Replace("_", " "));

        private static string Truncate(string s, int maxLen) =>
            s.Length <= maxLen ? s : s[..maxLen] + "…";
    }
}
