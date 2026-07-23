// DataManipulator.cs
// Feature 3 core visual: loads a data object and animates field mutations.
// Each field appears as a labelled row; changed values fly from old → new
// with a colour flash and particle burst.

using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using TMPro;

namespace Xoltra.Simulation
{
    public class DataManipulator : MonoBehaviour
    {
        // ── Inspector ─────────────────────────────────────────────────────────
        public GameObject FieldRowPrefab;       // Prefab: two TextMeshPro (key, value) + MeshRenderer bg
        public float      RowHeight     = 0.7f;
        public float      MutateFlash   = 0.4f; // seconds for color flash on mutation

        // ── Runtime ───────────────────────────────────────────────────────────
        private readonly Dictionary<string, GameObject> _objects = new();  // obj_id → container
        private readonly Dictionary<string, Dictionary<string, GameObject>> _fields = new();

        // ═════════════════════════════════════════════════════════════════════
        // LOAD OBJECT
        // ═════════════════════════════════════════════════════════════════════

        public void LoadObject(Dictionary<string, object> p)
        {
            string objId  = XoltraSimManager.GetStr(p, "obj_id");
            string label  = XoltraSimManager.GetStr(p, "label", "Data Object");
            var    data   = p.TryGetValue("data", out var d) ?
                            d as Dictionary<string, object> : null;

            if (data == null) return;

            // Container
            var container = new GameObject($"DataObj_{objId}");
            container.transform.parent   = transform;
            container.transform.position = Vector3.zero;

            // Title
            var titleGo = new GameObject("Title");
            titleGo.transform.parent   = container.transform;
            titleGo.transform.localPosition = new Vector3(0f, data.Count * RowHeight * 0.5f + 0.8f, 0f);
            var tmp = titleGo.AddComponent<TextMeshPro>();
            tmp.text      = label;
            tmp.color     = new Color(0.957f, 0.651f, 0.137f);
            tmp.fontSize  = 4f;
            tmp.alignment = TextAlignmentOptions.Center;

            // Field rows
            var fieldMap = new Dictionary<string, GameObject>();
            int idx = 0;
            foreach (var kv in data)
            {
                float y = (data.Count - idx - 1) * RowHeight - data.Count * RowHeight / 2f;
                var row = SpawnFieldRow(container.transform, kv.Key, FormatValue(kv.Value), y);
                fieldMap[kv.Key] = row;
                idx++;
            }

            _objects[objId] = container;
            _fields[objId]  = fieldMap;

            // Animate in
            container.transform.localScale = Vector3.zero;
            StartCoroutine(ScaleTo(container.transform, 1f, 0.35f));
        }

        // ═════════════════════════════════════════════════════════════════════
        // MUTATE FIELD
        // ═════════════════════════════════════════════════════════════════════

        public void MutateField(Dictionary<string, object> p)
        {
            string objId     = XoltraSimManager.GetStr(p, "obj_id");
            string fieldPath = XoltraSimManager.GetStr(p, "field_path");
            string oldVal    = XoltraSimManager.GetStr(p, "old_value", "—");
            string newVal    = XoltraSimManager.GetStr(p, "new_value", "—");

            // fieldPath may be "parent.child" — use the last segment as the display key
            string displayKey = fieldPath.Contains(".")
                                ? fieldPath.Substring(fieldPath.LastIndexOf('.') + 1)
                                : fieldPath;

            if (!_fields.TryGetValue(objId, out var fieldMap)) return;
            if (!fieldMap.TryGetValue(displayKey, out var row))
            {
                // New field — add a row
                if (_objects.TryGetValue(objId, out var container))
                {
                    float y = -fieldMap.Count * RowHeight - 0.5f;
                    row     = SpawnFieldRow(container.transform, displayKey, newVal, y);
                    fieldMap[displayKey] = row;
                }
                return;
            }

            StartCoroutine(AnimateMutation(row, oldVal, newVal));
        }

        private IEnumerator AnimateMutation(GameObject row, string oldVal, string newVal)
        {
            var valText = row.transform.Find("ValueText")?.GetComponent<TextMeshPro>();
            var bg      = row.GetComponentInChildren<MeshRenderer>();

            if (valText != null) valText.text = oldVal;

            // Flash old value red
            if (bg != null)
            {
                float e = 0f;
                Color start = bg.material.color;
                while (e < MutateFlash / 2f)
                {
                    e += Time.deltaTime;
                    bg.material.color = Color.Lerp(start, new Color(0.937f, 0.341f, 0.270f, 0.5f),
                                                   e / (MutateFlash / 2f));
                    yield return null;
                }
            }

            // Swap to new value with green flash
            if (valText != null) valText.text = newVal;

            if (bg != null)
            {
                float e = 0f;
                while (e < MutateFlash)
                {
                    e += Time.deltaTime;
                    bg.material.color = Color.Lerp(
                        new Color(0.133f, 0.722f, 0.647f, 0.5f),
                        new Color(0.141f, 0.141f, 0.165f, 0.8f),
                        e / MutateFlash
                    );
                    yield return null;
                }
                bg.material.color = new Color(0.141f, 0.141f, 0.165f, 0.8f);
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        // ANIMATE TRANSFORM
        // ═════════════════════════════════════════════════════════════════════

        public void AnimateTransform(Dictionary<string, object> p)
        {
            string objId = XoltraSimManager.GetStr(p, "obj_id");
            if (!_objects.TryGetValue(objId, out var go)) return;

            if (p.TryGetValue("target_position", out var rawPos))
            {
                var pos = rawPos as Dictionary<string, object>;
                if (pos != null)
                {
                    var target = new Vector3(
                        XoltraSimManager.GetFloat(pos, "x"),
                        XoltraSimManager.GetFloat(pos, "y"),
                        XoltraSimManager.GetFloat(pos, "z")
                    );
                    StartCoroutine(MoveTo(go.transform, target, 0.5f));
                }
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        // SHOW DIFF (renders a side-by-side before/after panel)
        // ═════════════════════════════════════════════════════════════════════

        public void ShowDiff(Dictionary<string, object> p)
        {
            // Spawn a temporary overlay text showing the diff summary
            string summary = XoltraSimManager.GetStr(p, "summary", "No diff data");
            var go = new GameObject("DiffOverlay");
            go.transform.parent   = transform;
            go.transform.position = new Vector3(0f, -4f, 0f);
            var tmp = go.AddComponent<TextMeshPro>();
            tmp.text      = summary;
            tmp.fontSize  = 2.8f;
            tmp.color     = new Color(0.957f, 0.651f, 0.137f);
            tmp.alignment = TextAlignmentOptions.Center;

            StartCoroutine(FadeOut(go, 4f));
        }

        // ═════════════════════════════════════════════════════════════════════
        // CLEAR
        // ═════════════════════════════════════════════════════════════════════

        public void ClearAll()
        {
            StopAllCoroutines();
            foreach (var go in _objects.Values) Destroy(go);
            _objects.Clear();
            _fields.Clear();

            foreach (Transform child in transform) Destroy(child.gameObject);
        }

        // ═════════════════════════════════════════════════════════════════════
        // HELPERS
        // ═════════════════════════════════════════════════════════════════════

        private GameObject SpawnFieldRow(Transform parent, string key, string value, float y)
        {
            var row = FieldRowPrefab != null
                      ? Instantiate(FieldRowPrefab, parent)
                      : BuildFieldRow(parent);

            row.transform.localPosition = new Vector3(0f, y, 0f);
            SetChildText(row, "KeyText",   key);
            SetChildText(row, "ValueText", value);
            return row;
        }

        private static GameObject BuildFieldRow(Transform parent)
        {
            // Fallback: build a row from primitives if no prefab is assigned
            var row = new GameObject("FieldRow");
            row.transform.parent = parent;

            // Background
            var bg       = GameObject.CreatePrimitive(PrimitiveType.Quad);
            bg.name      = "BG";
            bg.transform.parent        = row.transform;
            bg.transform.localPosition = Vector3.zero;
            bg.transform.localScale    = new Vector3(7f, 0.55f, 1f);
            bg.GetComponent<MeshRenderer>().material.color = new Color(0.141f, 0.141f, 0.165f, 0.8f);
            Destroy(bg.GetComponent<Collider>());

            // Key text
            var keyGo       = new GameObject("KeyText");
            keyGo.transform.parent        = row.transform;
            keyGo.transform.localPosition = new Vector3(-2.8f, 0f, -0.01f);
            var keyTmp = keyGo.AddComponent<TextMeshPro>();
            keyTmp.fontSize  = 2.4f;
            keyTmp.color     = new Color(0.420f, 0.420f, 0.470f);
            keyTmp.alignment = TextAlignmentOptions.MidlineLeft;

            // Value text
            var valGo       = new GameObject("ValueText");
            valGo.transform.parent        = row.transform;
            valGo.transform.localPosition = new Vector3(1.0f, 0f, -0.01f);
            var valTmp = valGo.AddComponent<TextMeshPro>();
            valTmp.fontSize  = 2.4f;
            valTmp.color     = new Color(0.910f, 0.910f, 0.925f);
            valTmp.alignment = TextAlignmentOptions.MidlineLeft;

            return row;
        }

        private static void SetChildText(GameObject row, string childName, string text)
        {
            var t = row.transform.Find(childName);
            if (t == null) return;
            var tmp = t.GetComponent<TextMeshPro>();
            if (tmp != null) tmp.text = text;
        }

        private static string FormatValue(object v)
        {
            if (v == null) return "null";
            if (v is bool b) return b ? "true" : "false";
            string s = v.ToString();
            return s.Length > 60 ? s[..60] + "…" : s;
        }

        private IEnumerator ScaleTo(Transform t, float target, float dur)
        {
            float e = 0f;
            while (e < dur) { e += Time.deltaTime; t.localScale = Vector3.one * (e / dur * target); yield return null; }
            t.localScale = Vector3.one * target;
        }

        private IEnumerator MoveTo(Transform t, Vector3 target, float dur)
        {
            Vector3 start = t.position;
            float   e     = 0f;
            while (e < dur) { e += Time.deltaTime; t.position = Vector3.Lerp(start, target, e / dur); yield return null; }
            t.position = target;
        }

        private IEnumerator FadeOut(GameObject go, float delay)
        {
            yield return new WaitForSeconds(delay);
            float dur = 0.5f;
            float e   = 0f;
            var   tmp = go.GetComponent<TextMeshPro>();
            if (tmp == null) { Destroy(go); yield break; }
            Color c   = tmp.color;
            while (e < dur) { e += Time.deltaTime; tmp.color = new Color(c.r, c.g, c.b, 1f - e / dur); yield return null; }
            Destroy(go);
        }
    }
}
