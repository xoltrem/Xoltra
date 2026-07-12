// NodeRenderer.cs
// Spawns, updates, and removes knowledge graph nodes and edges in the scene.
// Uses a pool of prefabs: NodePrefab (sphere/hex) and EdgePrefab (LineRenderer).
//
// Prefab requirements:
//   NodePrefab   — MeshRenderer + NodeView component + Collider
//   EdgePrefab   — LineRenderer (positions[0] and positions[1] set at runtime)

using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using TMPro;

namespace Xoltra.Simulation
{
    public class NodeRenderer : MonoBehaviour
    {
        // ── Inspector ─────────────────────────────────────────────────────────
        [Header("Prefabs")]
        public GameObject NodePrefab;
        public GameObject EdgePrefab;

        [Header("Appearance")]
        public float NodeScale      = 0.9f;
        public float EdgeWidth      = 0.04f;
        public float SpawnDuration  = 0.35f;

        // ── Runtime state ─────────────────────────────────────────────────────
        private readonly Dictionary<string, GameObject> _nodes = new();
        private readonly Dictionary<string, GameObject> _edges = new();

        // ═════════════════════════════════════════════════════════════════════
        // NODE CRUD
        // ═════════════════════════════════════════════════════════════════════

        public void RenderNode(Dictionary<string, object> p)
        {
            string nodeId   = XoltraSimManager.GetStr(p, "node_id");
            string nodeType = XoltraSimManager.GetStr(p, "node_type", "insight");
            string label    = XoltraSimManager.GetStr(p, "label",    "Node");
            string summary  = XoltraSimManager.GetStr(p, "summary",  "");
            float  relevance = XoltraSimManager.GetFloat(p, "relevance", 0.5f);
            string colorHex = XoltraSimManager.GetStr(p, "color", "#6B6B78");
            Vector3 pos     = ExtractPosition(p);

            if (_nodes.TryGetValue(nodeId, out var existing))
            {
                UpdateNodeVisual(existing, label, summary, colorHex, relevance);
                return;
            }

            var go  = Instantiate(NodePrefab, pos, Quaternion.identity, transform);
            go.name = $"Node_{nodeId}";
            go.transform.localScale = Vector3.zero;

            var view = go.GetComponent<NodeView>() ?? go.AddComponent<NodeView>();
            view.Initialise(nodeId, nodeType, label, summary, colorHex, relevance);

            // Wire click callback
            var click = go.GetComponent<NodeClickHandler>() ?? go.AddComponent<NodeClickHandler>();
            click.Setup(nodeId, nodeType);

            _nodes[nodeId] = go;

            // Pop-in animation
            StartCoroutine(ScaleTo(go.transform, NodeScale, SpawnDuration));
        }

        public void UpdateNode(Dictionary<string, object> p)
        {
            string nodeId  = XoltraSimManager.GetStr(p, "node_id");
            if (!_nodes.TryGetValue(nodeId, out var go)) return;
            UpdateNodeVisual(
                go,
                XoltraSimManager.GetStr(p, "label",    ""),
                XoltraSimManager.GetStr(p, "summary",  ""),
                XoltraSimManager.GetStr(p, "color",    "#6B6B78"),
                XoltraSimManager.GetFloat(p, "relevance", 0.5f)
            );
        }

        public void RemoveNode(string nodeId)
        {
            if (!_nodes.TryGetValue(nodeId, out var go)) return;
            _nodes.Remove(nodeId);
            StartCoroutine(ScaleTo(go.transform, 0f, 0.2f, () => Destroy(go)));
        }

        private static void UpdateNodeVisual(
            GameObject go, string label, string summary, string colorHex, float relevance)
        {
            var view = go.GetComponent<NodeView>();
            if (view == null) return;
            if (!string.IsNullOrEmpty(label))   view.SetLabel(label);
            if (!string.IsNullOrEmpty(summary)) view.SetSummary(summary);
            if (!string.IsNullOrEmpty(colorHex)) view.SetColor(colorHex);
            view.SetRelevance(relevance);
        }

        // ═════════════════════════════════════════════════════════════════════
        // EDGES
        // ═════════════════════════════════════════════════════════════════════

        public void RenderEdge(Dictionary<string, object> p)
        {
            string fromId    = XoltraSimManager.GetStr(p, "from_id");
            string toId      = XoltraSimManager.GetStr(p, "to_id");
            string edgeType  = XoltraSimManager.GetStr(p, "edge_type",  "relates_to");
            float  strength  = XoltraSimManager.GetFloat(p, "strength", 0.5f);
            string edgeKey   = $"{fromId}→{toId}";

            if (_edges.ContainsKey(edgeKey)) return;

            if (!_nodes.TryGetValue(fromId, out var fromGo) ||
                !_nodes.TryGetValue(toId,   out var toGo)) return;

            var go  = Instantiate(EdgePrefab, Vector3.zero, Quaternion.identity, transform);
            go.name = $"Edge_{edgeKey}";

            var lr = go.GetComponent<LineRenderer>();
            if (lr != null)
            {
                lr.positionCount = 2;
                lr.SetPosition(0, fromGo.transform.position);
                lr.SetPosition(1, toGo.transform.position);
                lr.startWidth = EdgeWidth * strength;
                lr.endWidth   = EdgeWidth * strength;

                // Edge color by type
                lr.material.color = EdgeColor(edgeType);
                lr.material.SetColor("_EmissionColor", EdgeColor(edgeType) * 0.4f);

                // Track node positions each frame
                go.AddComponent<EdgeTracker>().Setup(lr, fromGo.transform, toGo.transform);
            }

            _edges[edgeKey] = go;
        }

        private static Color EdgeColor(string edgeType) => edgeType switch
        {
            "derives_from"     => new Color(0.306f, 0.624f, 1f),       // blue
            "relates_to"       => new Color(0.420f, 0.420f, 0.470f),   // muted
            "evolved_from"     => new Color(0.659f, 0.333f, 0.969f),   // purple
            "prerequisite_for" => new Color(0.133f, 0.722f, 0.647f),   // teal
            "similar_to"       => new Color(0.957f, 0.651f, 0.137f),   // amber
            _                  => new Color(0.420f, 0.420f, 0.470f),
        };

        // ═════════════════════════════════════════════════════════════════════
        // HIGHLIGHT
        // ═════════════════════════════════════════════════════════════════════

        public void HighlightNode(string nodeId, string colorHex, bool pulse)
        {
            if (!_nodes.TryGetValue(nodeId, out var go)) return;
            var view = go.GetComponent<NodeView>();
            if (view == null) return;
            view.SetColor(colorHex);
            if (pulse) view.StartPulse();
        }

        public void HighlightPath(Dictionary<string, object> p)
        {
            // Highlight a chain of node IDs
            if (!p.TryGetValue("node_ids", out var raw)) return;
            var ids = raw as List<object>;
            if (ids == null) return;
            foreach (var id in ids)
                HighlightNode(id.ToString(), "#F5A623", false);
        }

        // ═════════════════════════════════════════════════════════════════════
        // CLEAR
        // ═════════════════════════════════════════════════════════════════════

        public void ClearAll()
        {
            foreach (var go in _nodes.Values)  Destroy(go);
            foreach (var go in _edges.Values)  Destroy(go);
            _nodes.Clear();
            _edges.Clear();
        }

        // ═════════════════════════════════════════════════════════════════════
        // HELPERS
        // ═════════════════════════════════════════════════════════════════════

        private static Vector3 ExtractPosition(Dictionary<string, object> p)
        {
            if (!p.TryGetValue("position", out var raw)) return Vector3.zero;
            var pos = raw as Dictionary<string, object>;
            if (pos == null) return Vector3.zero;
            return new Vector3(
                XoltraSimManager.GetFloat(pos, "x"),
                XoltraSimManager.GetFloat(pos, "y"),
                XoltraSimManager.GetFloat(pos, "z")
            );
        }

        private IEnumerator ScaleTo(
            Transform t, float target, float duration, System.Action onDone = null)
        {
            float start    = t.localScale.x;
            float elapsed  = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float s  = Mathf.Lerp(start, target, elapsed / duration);
                t.localScale = Vector3.one * s;
                yield return null;
            }
            t.localScale = Vector3.one * target;
            onDone?.Invoke();
        }
    }

    // ── NodeView — visual state for a single node ─────────────────────────────
    public class NodeView : MonoBehaviour
    {
        private string        _nodeId;
        private MeshRenderer  _mesh;
        private TextMeshPro   _labelText;
        private Coroutine     _pulseCoroutine;

        public void Initialise(string nodeId, string nodeType, string label,
                               string summary, string colorHex, float relevance)
        {
            _nodeId     = nodeId;
            _mesh       = GetComponentInChildren<MeshRenderer>();
            _labelText  = GetComponentInChildren<TextMeshPro>();

            SetColor(colorHex);
            SetLabel(label);
            SetRelevance(relevance);

            // Tooltip on hover (TextMeshPro world-space canvas — see SimulationUI)
            var tt = GetComponent<NodeTooltip>() ?? gameObject.AddComponent<NodeTooltip>();
            tt.SetContent(label, summary, nodeType);
        }

        public void SetLabel(string label)
        {
            if (_labelText != null) _labelText.text = label;
        }

        public void SetSummary(string summary)
        {
            var tt = GetComponent<NodeTooltip>();
            if (tt != null) tt.SetSummary(summary);
        }

        public void SetColor(string hex)
        {
            if (_mesh == null) return;
            if (ColorUtility.TryParseHtmlString(hex, out var c))
            {
                _mesh.material.color         = c;
                _mesh.material.SetColor("_EmissionColor", c * 0.3f);
            }
        }

        public void SetRelevance(float r)
        {
            // Scale node size slightly by relevance (0.7 → 1.0 range)
            float s = Mathf.Lerp(0.7f, 1.0f, Mathf.Clamp01(r));
            transform.localScale = Vector3.one * s;
        }

        public void StartPulse()
        {
            if (_pulseCoroutine != null) StopCoroutine(_pulseCoroutine);
            _pulseCoroutine = StartCoroutine(PulseLoop());
        }

        private IEnumerator PulseLoop()
        {
            float baseScale = transform.localScale.x;
            for (int i = 0; i < 3; i++)
            {
                float t = 0f;
                while (t < 1f)
                {
                    t += Time.deltaTime / 0.3f;
                    transform.localScale = Vector3.one * baseScale *
                        (1f + 0.2f * Mathf.Sin(t * Mathf.PI));
                    yield return null;
                }
            }
            transform.localScale = Vector3.one * baseScale;
        }
    }

    // ── EdgeTracker — keeps LineRenderer endpoints on node positions ──────────
    public class EdgeTracker : MonoBehaviour
    {
        private LineRenderer _lr;
        private Transform    _from, _to;

        public void Setup(LineRenderer lr, Transform from, Transform to)
        {
            _lr = lr; _from = from; _to = to;
        }

        private void LateUpdate()
        {
            if (_lr == null || _from == null || _to == null) return;
            _lr.SetPosition(0, _from.position);
            _lr.SetPosition(1, _to.position);
        }
    }

    // ── NodeClickHandler ──────────────────────────────────────────────────────
    public class NodeClickHandler : MonoBehaviour
    {
        private string _nodeId, _nodeType;

        public void Setup(string nodeId, string nodeType)
        {
            _nodeId = nodeId; _nodeType = nodeType;
        }

        private void OnMouseDown()
        {
            FindObjectOfType<XoltraWebSocket>()?.SendNodeClicked(_nodeId, _nodeType);
        }
    }

    // ── NodeTooltip ───────────────────────────────────────────────────────────
    public class NodeTooltip : MonoBehaviour
    {
        private string _title, _summary, _type;
        public void SetContent(string title, string summary, string type)
        {
            _title = title; _summary = summary; _type = type;
        }
        public void SetSummary(string s) { _summary = s; }
        public string Title   => _title;
        public string Summary => _summary;
        public string Type    => _type;
    }
}
