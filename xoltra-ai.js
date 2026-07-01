/**
 * xoltra-ai.js
 * Pure logic module — no UI. Import and call from your own frontend.
 *
 * STORAGE KEYS (window.storage, persists across sessions):
 *   xoltra:traits    — learned user profile (6 fields, ~200 bytes)
 *   xoltra:settings  — mode + custom prompt
 *   xoltra:history   — last 20 messages for cross-session context
 *
 * QUICK START:
 *   import { xoltra } from './xoltra-ai.js';
 *   await xoltra.init();
 *   const reply = await xoltra.send("your message");
 *
 * SETTINGS (call from your settings UI):
 *   await xoltra.setSettings({ mode: 'adaptive' });   // auto-learn
 *   await xoltra.setSettings({ mode: 'custom', customPrompt: 'You are...' });
 *   await xoltra.setSettings({ mode: 'off' });        // plain AI
 *
 * PROFILE (call from your settings UI):
 *   xoltra.getTraits()     // → current learned profile object or null
 *   xoltra.getSettings()   // → { mode, customPrompt }
 *   xoltra.getHistory()    // → message array
 *   await xoltra.resetTraits()
 *   await xoltra.clearHistory()
 *
 * LISTENING FOR STATE CHANGES (update your UI when traits are extracted):
 *   xoltra.onChange((state) => {
 *     // state: { traits, settings, loading, extracting }
 *     // update your trait display, mode badge, loading indicator etc.
 *   });
 */

const SK = {
  traits:   'xoltra:traits',
  settings: 'xoltra:settings',
  history:  'xoltra:history',
};

const DEFAULTS = { mode: 'adaptive', customPrompt: '' };
const EXTRACT_EVERY = 4;  // extract traits every N user messages
const MAX_HISTORY = 20;

// ── storage helpers ──────────────────────────────────────────────────────────
async function sGet(k) {
  try { const r = await window.storage.get(k); return r ? JSON.parse(r.value) : null; }
  catch { return null; }
}
async function sSet(k, v) { try { await window.storage.set(k, JSON.stringify(v)); } catch {} }
async function sDel(k)    { try { await window.storage.delete(k); } catch {} }

// ── system prompt builder ────────────────────────────────────────────────────
function buildSystemPrompt(traits, settings) {
  if (settings.mode === 'off') {
    return 'You are a helpful AI assistant.';
  }
  if (settings.mode === 'custom' && settings.customPrompt?.trim()) {
    return settings.customPrompt.trim();
  }
  if (!traits) {
    return 'You are a helpful AI. Pay close attention to how this user communicates and naturally adapt your style, vocabulary and tone to match theirs. Never acknowledge you are doing this.';
  }
  return [
    'You are a personalised AI assistant. Adapt every response precisely to this user\'s profile.',
    `Vocabulary: ${traits.vocabulary} — match their word complexity exactly.`,
    `Style: ${traits.communication}. Tone: ${traits.tone}.`,
    `Reasoning: ${traits.reasoning} — mirror their thinking structure.`,
    traits.interests?.length ? `Interests: ${traits.interests.join(', ')} — weave in naturally when relevant.` : '',
    traits.expertise?.length ? `Expertise: ${traits.expertise.join(', ')} — skip over-explaining in these areas.` : '',
    'Never acknowledge you are adapting. Just be that version of yourself.',
  ].filter(Boolean).join('\n');
}

// ── API calls ────────────────────────────────────────────────────────────────
async function _chat(systemPrompt, messages) {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 1000,
      system: systemPrompt,
      messages: messages.map(m => ({ role: m.role, content: m.content })),
    }),
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error.message);
  return data.content?.map(b => b.text || '').join('') || '';
}

async function _extractTraits(messages, existing) {
  const userMsgs = messages
    .filter(m => m.role === 'user')
    .slice(-12)
    .map(m => m.content)
    .join('\n---\n');

  const prompt = `Analyze these messages and extract the user's key communication traits. Return ONLY valid JSON, no markdown.

Messages:
${userMsgs}
${existing ? `\nExisting profile to refine (merge, do not discard): ${JSON.stringify(existing)}` : ''}

Return exactly this JSON:
{"vocabulary":"technical|intermediate|casual","reasoning":"analytical|intuitive|practical|creative","communication":"concise|detailed|conversational","tone":"formal|casual|playful","interests":[],"expertise":[]}

interests and expertise: max 3 items each, only include if clearly evidenced. Empty [] if unclear.`;

  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 200,
      messages: [{ role: 'user', content: prompt }],
    }),
  });
  const data = await res.json();
  const text = data.content?.map(b => b.text || '').join('') || '{}';
  return { ...JSON.parse(text.replace(/```json|```/g, '').trim()), updatedAt: Date.now() };
}

// ── core class ───────────────────────────────────────────────────────────────
class XoltraAI {
  constructor() {
    this._settings = { ...DEFAULTS };
    this._traits   = null;
    this._history  = [];
    this._msgCount = 0;
    this._loading  = false;
    this._extracting = false;
    this._listeners = [];
  }

  // ── init ──
  async init() {
    const [s, t, h] = await Promise.all([
      sGet(SK.settings),
      sGet(SK.traits),
      sGet(SK.history),
    ]);
    if (s) this._settings = s;
    if (t) this._traits   = t;
    if (h?.length) this._history = h;
    return this; // chainable: await xoltra.init()
  }

  // ── send a message, returns the AI reply string ──
  async send(userText) {
    if (!userText?.trim()) throw new Error('Empty message');
    if (this._loading) throw new Error('Already processing a message');

    const userMsg = { role: 'user', content: userText.trim() };
    this._history = [...this._history, userMsg];
    this._msgCount++;
    this._loading = true;
    this._emit();

    try {
      const systemPrompt = buildSystemPrompt(this._traits, this._settings);
      const reply = await _chat(systemPrompt, this._history);

      const assistantMsg = { role: 'assistant', content: reply };
      this._history = [...this._history, assistantMsg].slice(-MAX_HISTORY);
      await sSet(SK.history, this._history);

      // background trait extraction (non-blocking)
      if (this._settings.mode === 'adaptive' && this._msgCount >= EXTRACT_EVERY) {
        this._msgCount = 0;
        this._extracting = true;
        this._emit();
        _extractTraits(this._history, this._traits)
          .then(async extracted => {
            this._traits = extracted;
            await sSet(SK.traits, extracted);
          })
          .catch(() => {})
          .finally(() => { this._extracting = false; this._emit(); });
      }

      this._loading = false;
      this._emit();
      return reply;

    } catch (err) {
      this._loading = false;
      this._emit();
      throw err;
    }
  }

  // ── settings ──
  getSettings() { return { ...this._settings }; }

  async setSettings(patch) {
    this._settings = { ...this._settings, ...patch };
    await sSet(SK.settings, this._settings);
    this._emit();
  }

  // ── traits ──
  getTraits() { return this._traits ? { ...this._traits } : null; }

  async resetTraits() {
    this._traits = null;
    await sDel(SK.traits);
    this._emit();
  }

  // ── history ──
  getHistory() { return [...this._history]; }

  async clearHistory() {
    this._history = [];
    this._msgCount = 0;
    await sDel(SK.history);
    this._emit();
  }

  // ── state snapshot (for your UI) ──
  getState() {
    return {
      traits:     this.getTraits(),
      settings:   this.getSettings(),
      history:    this.getHistory(),
      loading:    this._loading,
      extracting: this._extracting,
    };
  }

  // ── change listener (wire up to your UI) ──
  onChange(fn) {
    this._listeners.push(fn);
    return () => { this._listeners = this._listeners.filter(l => l !== fn); }; // returns unsubscribe fn
  }

  _emit() {
    const state = this.getState();
    this._listeners.forEach(fn => { try { fn(state); } catch {} });
  }
}

// ── singleton export ─────────────────────────────────────────────────────────
export const xoltra = new XoltraAI();
export default xoltra;

/**
 * TRAIT OBJECT SHAPE (stored at xoltra:traits):
 * {
 *   vocabulary:    "technical" | "intermediate" | "casual"
 *   reasoning:     "analytical" | "intuitive" | "practical" | "creative"
 *   communication: "concise" | "detailed" | "conversational"
 *   tone:          "formal" | "casual" | "playful"
 *   interests:     string[]   // e.g. ["AI", "security"]
 *   expertise:     string[]   // e.g. ["Python", "system design"]
 *   updatedAt:     number     // timestamp
 * }
 *
 * SETTINGS OBJECT SHAPE (stored at xoltra:settings):
 * {
 *   mode:         "adaptive" | "custom" | "off"
 *   customPrompt: string
 * }
 */
