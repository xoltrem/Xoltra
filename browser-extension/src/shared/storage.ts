/**
 * storage.ts — typed helpers over chrome.storage.
 *
 * Tiers, chosen deliberately:
 *   chrome.storage.local   — settings + auth token (survives restarts).
 *   chrome.storage.session — session-only workflow overrides + last page
 *                            context (cleared when the browser closes; also
 *                            not synced and not readable by content scripts
 *                            by default — the right tier for transient data).
 */
import { DEFAULT_SETTINGS, type PageContext, type SessionOverrides, type Settings } from './types';

const TOKEN_KEY = 'xoltra_token'; // same name the web app uses in localStorage
const SETTINGS_KEY = 'xoltra_settings';
const OVERRIDES_KEY = 'xoltra_session_overrides';
const CONTEXT_KEY = 'xoltra_page_context';

// ─── Auth token ──────────────────────────────────────────────────────────────

export async function getToken(): Promise<string | null> {
  const r = await chrome.storage.local.get(TOKEN_KEY);
  return (r[TOKEN_KEY] as string | undefined) ?? null;
}

export async function setToken(token: string | null): Promise<void> {
  if (token) await chrome.storage.local.set({ [TOKEN_KEY]: token });
  else await chrome.storage.local.remove(TOKEN_KEY);
}

// ─── Settings ────────────────────────────────────────────────────────────────

export async function getSettings(): Promise<Settings> {
  const r = await chrome.storage.local.get(SETTINGS_KEY);
  return { ...DEFAULT_SETTINGS, ...(r[SETTINGS_KEY] as Partial<Settings> | undefined) };
}

export async function setSettings(patch: Partial<Settings>): Promise<Settings> {
  const merged = { ...(await getSettings()), ...patch };
  await chrome.storage.local.set({ [SETTINGS_KEY]: merged });
  return merged;
}

// ─── Session-only overrides ──────────────────────────────────────────────────

export async function getOverrides(): Promise<SessionOverrides> {
  const r = await chrome.storage.session.get(OVERRIDES_KEY);
  return (r[OVERRIDES_KEY] as SessionOverrides | undefined) ?? {};
}

export async function setWorkflowOverrides(
  workflowId: string,
  overrides: Record<string, Record<string, unknown>> | null,
): Promise<SessionOverrides> {
  const all = await getOverrides();
  if (overrides && Object.keys(overrides).length > 0) all[workflowId] = overrides;
  else delete all[workflowId];
  await chrome.storage.session.set({ [OVERRIDES_KEY]: all });
  return all;
}

// ─── Captured page context ───────────────────────────────────────────────────

export async function getPageContext(): Promise<PageContext | null> {
  const r = await chrome.storage.session.get(CONTEXT_KEY);
  return (r[CONTEXT_KEY] as PageContext | undefined) ?? null;
}

export async function setPageContext(ctx: PageContext | null): Promise<void> {
  if (ctx) await chrome.storage.session.set({ [CONTEXT_KEY]: ctx });
  else await chrome.storage.session.remove(CONTEXT_KEY);
}
