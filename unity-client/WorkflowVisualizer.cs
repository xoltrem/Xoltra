// WorkflowVisualizer.cs
// Renders an ArchitectAgent workflow as a vertical phase/step timeline.
// Phases spawn as wide pill nodes; steps spawn as smaller rectangles below.
// Progress is tracked per-step and per-phase with color transitions.

using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using TMPro;

namespace Xoltra.Simulation
{
    public class WorkflowVisualizer : MonoBehaviour
    {
        // ── Inspector ─────────────────────────────────────────────────────────
        [Header("Prefabs")]
        public GameObject PhasePrefab;
        public GameObject StepPrefab;
        public GameObject RiskPrefab;

        [Header("Layout")]
        public float PhaseYSpacing  = 3.5f;
        public float StepXSpacing   = 2.8f;
        public float StepYOffset    = -1.4f;
        public float SpawnDelay     = 0.08f;

        // ── Colors ────────────────────────────────────────────────────────────
        private static readonly Color ColPending  = new Color(0.420f, 0.420f, 0.470f);  // grey
        private static readonly Color ColActive   = new Color(0.957f, 0.651f, 0.137f);  // amber
        private static readonly Color ColDone     = new Color(0.133f, 0.722f, 0.647f);  // teal

        // ── Runtime ───────────────────────────────────────────────────────────
        private readonly List<PhaseNode>   _phases = new();
        private readonly List<GameObject>  _risks  = new();

        // ═════════════════════════════════════════════════════════════════════
        // RENDER
        // ═════════════════════════════════════════════════════════════════════

        public void RenderWorkflow(Dictionary<string, object> p)
        {
            ClearAll();

            string goalSummary = XoltraSimManager.GetStr(p, "goal_summary");
            var phases         = p.TryGetValue("phases", out var raw) ?
                                 raw as List<object> : null;
            var topRisks       = p.TryGetValue("top_risks", out var r) ?
                                 r as List<object> : null;

            if (phases == null) return;

            StartCoroutine(SpawnPhases(phases, goalSummary));

            if (topRisks != null)
                StartCoroutine(SpawnRisks(topRisks, phases.Count));
        }

        private IEnumerator SpawnPhases(List<object> phases, string goal)
        {
            // Goal banner at the top
            if (!string.IsNullOrEmpty(goal))
            {
                var banner = SpawnLabel(
                    $"⬡  {goal}",
                    new Vector3(0f, (phases.Count * PhaseYSpacing) / 2f + 1.2f, 0f),
                    new Color(0.957f, 0.651f, 0.137f)
                );
                banner.name = "GoalBanner";
            }

            for (int i = 0; i < phases.Count; i++)
            {
                var phaseData = phases[i] as Dictionary<string, object>;
                if (phaseData == null) continue;

                float yPos = (phases.Count - 1 - i) * PhaseYSpacing;
                var pn     = SpawnPhase(phaseData, i, new Vector3(0f, yPos, 0f));
                _phases.Add(pn);

                var steps = phaseData.TryGetValue("steps", out var sv) ?
                            sv as List<object> : null;
                if (steps != null)
                    yield return StartCoroutine(SpawnSteps(steps, i, yPos));

                yield return new WaitForSeconds(SpawnDelay);
            }
        }

        private PhaseNode SpawnPhase(Dictionary<string, object> d, int index, Vector3 pos)
        {
            var go  = Instantiate(PhasePrefab, pos, Quaternion.identity, transform);
            go.name = $"Phase_{index}";

            string name      = XoltraSimManager.GetStr(d, "phase_name", $"Phase {index + 1}");
            string objective = XoltraSimManager.GetStr(d, "objective", "");

            SetText(go, "LabelText", $"Phase {index + 1}: {name}");
            SetText(go, "ObjectiveText", objective);
            SetMeshColor(go, ColPending);

            var pn        = new PhaseNode { Go = go, PhaseIndex = index, StepNodes = new() };

            // Click to send phase_clicked event
            var clk = go.AddComponent<PhaseClickHandler>();
            clk.Setup(index);

            go.transform.localScale = Vector3.zero;
            StartCoroutine(ScaleTo(go.transform, 1f, 0.3f));

            return pn;
        }

        private IEnumerator SpawnSteps(List<object> steps, int phaseIdx, float phaseY)
        {
            int count    = steps.Count;
            float totalW = (count - 1) * StepXSpacing;

            for (int j = 0; j < count; j++)
            {
                var step = steps[j] as Dictionary<string, object>;
                if (step == null) continue;

                float xPos = j * StepXSpacing - totalW / 2f;
                float yPos = phaseY + StepYOffset;

                var go     = Instantiate(StepPrefab,
                             new Vector3(xPos, yPos, 0f), Quaternion.identity, transform);
                go.name    = $"Phase{phaseIdx}_Step{j}";

                string action     = XoltraSimManager.GetStr(step, "action", "Action");
                string difficulty = XoltraSimManager.GetStr(step, "difficulty", "Medium");
                string time       = XoltraSimManager.GetStr(step, "estimated_time", "");

                SetText(go, "ActionText",    TruncateWords(action, 7));
                SetText(go, "DifficultyText", difficulty);
                SetText(go, "TimeText",       time);
                SetMeshColor(go, ColPending);

                // Click handler
                var clk = go.AddComponent<StepClickHandler>();
                clk.Setup(phaseIdx, j);

                go.transform.localScale = Vector3.zero;
                StartCoroutine(ScaleTo(go.transform, 0.85f, 0.25f));

                if (_phases.Count > phaseIdx)
                    _phases[phaseIdx].StepNodes.Add(go);

                yield return new WaitForSeconds(SpawnDelay * 0.5f);
            }
        }

        private IEnumerator SpawnRisks(List<object> risks, int phaseCount)
        {
            yield return new WaitForSeconds(0.4f);

            float startX = -(risks.Count * 2.4f) / 2f;
            float y      = -phaseCount * PhaseYSpacing * 0.5f - 2.5f;

            SetText(
                SpawnLabel("⚠ TOP RISKS", new Vector3(0f, y + 0.9f, 0f),
                    new Color(0.937f, 0.341f, 0.270f)),
                "LabelText", "⚠ TOP RISKS"
            );

            for (int i = 0; i < Mathf.Min(risks.Count, 3); i++)
            {
                var risk = risks[i] as Dictionary<string, object>;
                if (risk == null) continue;

                var go  = Instantiate(RiskPrefab ?? StepPrefab,
                          new Vector3(startX + i * 2.4f, y, 0f),
                          Quaternion.identity, transform);
                go.name = $"Risk_{i}";

                string riskText = XoltraSimManager.GetStr(risk, "risk", "Risk");
                SetText(go, "ActionText", TruncateWords(riskText, 8));
                SetMeshColor(go, new Color(0.937f, 0.341f, 0.270f, 0.4f));
                _risks.Add(go);

                go.transform.localScale = Vector3.zero;
                StartCoroutine(ScaleTo(go.transform, 0.85f, 0.25f));
                yield return new WaitForSeconds(SpawnDelay);
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        // PROGRESS CONTROL
        // ═════════════════════════════════════════════════════════════════════

        public void AdvancePhase(int phaseIndex)
        {
            // Mark previous phases as done, current as active
            for (int i = 0; i < _phases.Count; i++)
            {
                Color c = i < phaseIndex ? ColDone : (i == phaseIndex ? ColActive : ColPending);
                SetMeshColor(_phases[i].Go, c);
            }
        }

        public void CompleteStep(int phaseIndex, int stepIndex)
        {
            if (phaseIndex >= _phases.Count) return;
            var stepNodes = _phases[phaseIndex].StepNodes;
            if (stepIndex >= stepNodes.Count) return;
            SetMeshColor(stepNodes[stepIndex], ColDone);

            // Check if all steps in phase are done
            bool allDone = true;
            foreach (var sn in stepNodes)
            {
                var mr = sn.GetComponentInChildren<MeshRenderer>();
                if (mr != null && mr.material.color != ColDone) { allDone = false; break; }
            }
            if (allDone) SetMeshColor(_phases[phaseIndex].Go, ColDone);
        }

        public void SetPhaseStatus(int phaseIndex, string status)
        {
            if (phaseIndex >= _phases.Count) return;
            Color c = status switch
            {
                "active"   => ColActive,
                "done"     => ColDone,
                "error"    => new Color(0.937f, 0.341f, 0.270f),
                _          => ColPending,
            };
            SetMeshColor(_phases[phaseIndex].Go, c);
        }

        // ═════════════════════════════════════════════════════════════════════
        // CLEAR
        // ═════════════════════════════════════════════════════════════════════

        public void ClearAll()
        {
            StopAllCoroutines();
            foreach (var pn in _phases)
            {
                foreach (var sn in pn.StepNodes) Destroy(sn);
                Destroy(pn.Go);
            }
            foreach (var go in _risks) Destroy(go);
            _phases.Clear();
            _risks.Clear();

            // Destroy any label banners
            foreach (Transform child in transform)
                Destroy(child.gameObject);
        }

        // ═════════════════════════════════════════════════════════════════════
        // UTILS
        // ═════════════════════════════════════════════════════════════════════

        private GameObject SpawnLabel(string text, Vector3 pos, Color color)
        {
            var go  = new GameObject("Label");
            go.transform.parent    = transform;
            go.transform.position  = pos;
            var tmp = go.AddComponent<TextMeshPro>();
            tmp.text      = text;
            tmp.color     = color;
            tmp.fontSize  = 3.5f;
            tmp.alignment = TextAlignmentOptions.Center;
            return go;
        }

        private static void SetText(GameObject go, string childName, string text)
        {
            var t = go.transform.Find(childName);
            if (t == null) return;
            var tmp = t.GetComponent<TextMeshPro>() ?? t.GetComponent<TextMeshProUGUI>();
            if (tmp != null) tmp.text = text;
        }

        private static void SetMeshColor(GameObject go, Color c)
        {
            var mr = go.GetComponentInChildren<MeshRenderer>();
            if (mr != null) mr.material.color = c;
        }

        private static string TruncateWords(string s, int words)
        {
            var parts = s.Split(' ');
            return parts.Length <= words ? s :
                   string.Join(" ", System.Array.GetRange(parts, 0, words)) + "…";
        }

        private IEnumerator ScaleTo(Transform t, float target, float dur)
        {
            float e = 0f;
            while (e < dur) { e += Time.deltaTime; t.localScale = Vector3.one * (e / dur * target); yield return null; }
            t.localScale = Vector3.one * target;
        }

        // ── Data model ────────────────────────────────────────────────────────
        private class PhaseNode
        {
            public GameObject      Go;
            public int             PhaseIndex;
            public List<GameObject> StepNodes;
        }
    }

    // ── Click handlers ────────────────────────────────────────────────────────
    public class PhaseClickHandler : MonoBehaviour
    {
        private int _pi;
        public void Setup(int phaseIndex) { _pi = phaseIndex; }
        private void OnMouseDown()
        {
            FindObjectOfType<XoltraWebSocket>()?.SendEvent(
                "phase_clicked", $"{{\"phase_index\":{_pi}}}");
        }
    }

    public class StepClickHandler : MonoBehaviour
    {
        private int _pi, _si;
        public void Setup(int pi, int si) { _pi = pi; _si = si; }
        private void OnMouseDown()
        {
            FindObjectOfType<XoltraWebSocket>()?.SendStepClicked(_pi, _si);
        }
    }
}
