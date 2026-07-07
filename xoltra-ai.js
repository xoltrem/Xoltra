/**
 * xoltra-ai.js
 * Fixed: was calling api.anthropic.com directly from browser (no key,
 * CORS-blocked, always fails) and using window.storage (not a real
 * browser API — nothing ever persisted). Now calls Xoltra's own
 * Flask backend (personalization.py) with JWT auth; localStorage
 * used as instant local cache, backend is source of truth (multi-tenant).
 *
 * QUICK START:
 *   import { xoltra } from './xoltra-ai.js';
 *   await xoltra.init();
 *   const reply = await xoltra.send("your message");
 *
 * SETTINGS:
 *   await xoltra.setSettings({ mode: 'adaptive' });
 *   await xoltra.setSettings({ mode: 'custom', customPrompt: 'You are...' });
 *   await xoltra.setSettings({ mode: 'off' });
 *
 * PROFILE:
 *   xoltra.getTraits()
 *   xoltra.getSettings()
 *   await xoltra.resetTraits()
 *   await xoltra.clearHistory()
 *
 * xoltra.onChange((state) => { ... })
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001';
const LK = { traits: 'xoltra:traits', settings: 'xoltra:settings' }; // local cache only

function getToken() {
  try { return localStorage.getItem('xoltra_token'); } catch { return null; }
}

async function api(path, opts = {}) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/personalization${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opts.headers,
    },
  });
  const data = await res.json();
  if (!res.ok || data.success === false) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function lGet(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } }
function lSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }
function lDel(k) { try { localStorage.removeItem(k); } catch {} }

class XoltraAI {
  constructor() {
    this._settings = { mode: 'adaptive', customPrompt: '' };
    this._traits = null;
    this._loading = false;
    this._extracting = false;
    this._listeners = [];
  }

  async init() {
    // instant paint from cache, then reconcile with backend (source of truth)
    this._settings = lGet(LK.settings) || this._settings;
    this._traits   = lGet(LK.traits) || null;
    this._emit();

    try {
      const { traits, settings } = await api('/profile');
      this._traits = traits;
      this._settings = settings;
      lSet(LK.traits, traits);
      lSet(LK.settings, settings);
      this._emit();
    } catch { /* offline — cached state stands */ }

    return this;
  }

  async send(userText) {
    if (!userText?.trim()) throw new Error('Empty message');
    if (this._loading) throw new Error('Already processing a message');

    this._loading = true;
    this._emit();

    try {
      const { reply, extracting } = await api('/chat', {
        method: 'POST',
        body: JSON.stringify({ message: userText.trim() }),
      });

      this._extracting = !!extracting;
      this._emit();

      if (extracting) {
        // trait extraction ran server-side (every 4 messages) — pull the refreshed profile
        api('/profile').then(({ traits }) => {
          this._traits = traits;
          lSet(LK.traits, traits);
          this._extracting = false;
          this._emit();
        }).catch(() => { this._extracting = false; this._emit(); });
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

  getSettings() { return { ...this._settings }; }

  async setSettings(patch) {
    const { settings } = await api('/settings', { method: 'PUT', body: JSON.stringify(patch) });
    this._settings = settings;
    lSet(LK.settings, settings);
    this._emit();
  }

  getTraits() { return this._traits ? { ...this._traits } : null; }

  async resetTraits() {
    await api('/traits', { method: 'DELETE' });
    this._traits = null;
    lDel(LK.traits);
    this._emit();
  }

  async clearHistory() {
    await api('/history', { method: 'DELETE' });
  }

  async getHistory() {
    const { history } = await api('/history');
    return history;
  }

  getState() {
    return {
      traits: this.getTraits(),
      settings: this.getSettings(),
      loading: this._loading,
      extracting: this._extracting,
    };
  }

  onChange(fn) {
    this._listeners.push(fn);
    return () => { this._listeners = this._listeners.filter(l => l !== fn); };
  }

  _emit() {
    const state = this.getState();
    this._listeners.forEach(fn => { try { fn(state); } catch {} });
  }
}

export const xoltra = new XoltraAI();
export default xoltra;

/**
 * TRAIT OBJECT SHAPE (mirrors backend personalization.py):
 * { vocabulary, reasoning, communication, tone, interests[], expertise[], updatedAt }
 * SETTINGS SHAPE: { mode: "adaptive"|"custom"|"off", customPrompt }
 */
