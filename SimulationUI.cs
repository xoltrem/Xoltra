// SimulationUI.cs
// Handles all HUD elements: toast notifications, status bar, connection badge.
// Attach to a UI Canvas GameObject. Drag UI element references into Inspector.

using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

namespace Xoltra.Simulation
{
    public class SimulationUI : MonoBehaviour
    {
        // ── Inspector — drag your Canvas children here ─────────────────────────
        [Header("Toast")]
        public RectTransform ToastContainer;   // vertical layout group
        public GameObject    ToastPrefab;       // Image + TextMeshProUGUI

        [Header("Status Bar")]
        public TextMeshProUGUI StatusText;
        public Slider          ProgressSlider;

        [Header("Connection Badge")]
        public Image           ConnectionDot;   // small circle
        public TextMeshProUGUI ConnectionLabel;

        // ── Colors ────────────────────────────────────────────────────────────
        private static readonly Color32 ColInfo    = new(74,  158, 255, 230);
        private static readonly Color32 ColSuccess = new(34,  197, 94,  230);
        private static readonly Color32 ColWarning = new(245, 166, 35,  230);
        private static readonly Color32 ColError   = new(239, 68,  68,  230);
        private static readonly Color32 ColConnected    = new(34,  197, 94,  255);
        private static readonly Color32 ColDisconnected = new(107, 107, 120, 255);

        // ── Runtime ───────────────────────────────────────────────────────────
        private readonly Queue<ToastData> _toastQueue   = new();
        private bool                       _toastRunning = false;

        // ═════════════════════════════════════════════════════════════════════
        // TOAST
        // ═════════════════════════════════════════════════════════════════════

        public void ShowToast(string message, string level = "info")
        {
            _toastQueue.Enqueue(new ToastData(message, level));
            if (!_toastRunning)
                StartCoroutine(DrainToastQueue());
        }

        private IEnumerator DrainToastQueue()
        {
            _toastRunning = true;
            while (_toastQueue.Count > 0)
            {
                var data = _toastQueue.Dequeue();
                yield return StartCoroutine(ShowToastCoroutine(data));
                yield return new WaitForSeconds(0.15f);
            }
            _toastRunning = false;
        }

        private IEnumerator ShowToastCoroutine(ToastData data)
        {
            if (ToastPrefab == null || ToastContainer == null) yield break;

            var go   = Instantiate(ToastPrefab, ToastContainer);
            var img  = go.GetComponent<Image>();
            var text = go.GetComponentInChildren<TextMeshProUGUI>();

            if (img  != null) img.color  = LevelColor(data.Level);
            if (text != null) text.text  = data.Message;

            // Slide in
            var rect = go.GetComponent<RectTransform>();
            yield return StartCoroutine(SlideIn(rect));

            yield return new WaitForSeconds(2.8f);

            // Fade out
            yield return StartCoroutine(FadeOut(go, 0.4f));
            Destroy(go);
        }

        private IEnumerator SlideIn(RectTransform rect)
        {
            Vector2 start  = new Vector2(300f, rect.anchoredPosition.y);
            Vector2 target = new Vector2(0f,   rect.anchoredPosition.y);
            float   e      = 0f;
            while (e < 0.25f)
            {
                e += Time.deltaTime;
                rect.anchoredPosition = Vector2.Lerp(start, target, e / 0.25f);
                yield return null;
            }
            rect.anchoredPosition = target;
        }

        private IEnumerator FadeOut(GameObject go, float dur)
        {
            var cg = go.GetComponent<CanvasGroup>() ?? go.AddComponent<CanvasGroup>();
            float e = 0f;
            while (e < dur) { e += Time.deltaTime; cg.alpha = 1f - e / dur; yield return null; }
        }

        // ═════════════════════════════════════════════════════════════════════
        // STATUS BAR
        // ═════════════════════════════════════════════════════════════════════

        public void UpdateStatusBar(string text, float progress = -1f)
        {
            if (StatusText != null)
                StatusText.text = text;

            if (ProgressSlider == null) return;

            if (progress < 0f)
            {
                // Indeterminate — animate the slider value
                StopCoroutine("IndeterminateProgress");
                StartCoroutine(IndeterminateProgress());
            }
            else
            {
                StopAllCoroutines();
                ProgressSlider.value = Mathf.Clamp01(progress);
            }
        }

        private IEnumerator IndeterminateProgress()
        {
            while (true)
            {
                float t = Mathf.PingPong(Time.time * 0.7f, 1f);
                if (ProgressSlider != null) ProgressSlider.value = t;
                yield return null;
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        // CONNECTION BADGE
        // ═════════════════════════════════════════════════════════════════════

        public void SetConnectionBadge(bool connected)
        {
            if (ConnectionDot   != null) ConnectionDot.color  = connected ? ColConnected : ColDisconnected;
            if (ConnectionLabel != null) ConnectionLabel.text  = connected ? "UNITY LIVE" : "DISCONNECTED";
        }

        // ═════════════════════════════════════════════════════════════════════
        // MODAL
        // ═════════════════════════════════════════════════════════════════════

        public void ShowModal(Dictionary<string, object> p)
        {
            // Simple implementation: show as a large toast
            string title   = XoltraSimManager.GetStr(p, "title",   "Notice");
            string message = XoltraSimManager.GetStr(p, "message", "");
            ShowToast($"{title}: {message}", "info");
        }

        // ═════════════════════════════════════════════════════════════════════
        // HELPERS
        // ═════════════════════════════════════════════════════════════════════

        private static Color32 LevelColor(string level) => level switch
        {
            "success" => ColSuccess,
            "warning" => ColWarning,
            "error"   => ColError,
            _         => ColInfo,
        };

        private struct ToastData
        {
            public string Message, Level;
            public ToastData(string m, string l) { Message = m; Level = l; }
        }
    }
}
