/**
 * hooks.ts — side panel state hooks.
 *
 * chrome.storage is the single source of truth (the MV3 worker is ephemeral,
 * extension pages open/close constantly). These hooks read once on mount and
 * subscribe to chrome.storage.onChanged, so every surface stays consistent
 * without a message bus.
 */
import { useCallback, useEffect, useState } from 'react';
import { getWorkflows } from '../shared/api';
import { onMessage, sendMessage } from '../shared/messages';
import { getOverrides, getPageContext, getSettings, getToken } from '../shared/storage';
import type { PageContext, SessionOverrides, Settings, WorkflowSummary } from '../shared/types';
import { DEFAULT_SETTINGS } from '../shared/types';

export function useToken(): { token: string | null; loading: boolean } {
  const [token, setTokenState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void getToken().then(t => { setTokenState(t); setLoading(false); });
    const listener = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === 'local' && changes.xoltra_token) {
        setTokenState((changes.xoltra_token.newValue as string | undefined) ?? null);
      }
    };
    chrome.storage.onChanged.addListener(listener);
    return () => chrome.storage.onChanged.removeListener(listener);
  }, []);

  return { token, loading };
}

export function useSettings(): Settings {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  useEffect(() => {
    void getSettings().then(setSettings);
    const listener = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === 'local' && changes.xoltra_settings) void getSettings().then(setSettings);
    };
    chrome.storage.onChanged.addListener(listener);
    return () => chrome.storage.onChanged.removeListener(listener);
  }, []);
  return settings;
}

export function usePageContext(): {
  context: PageContext | null;
  capture: () => Promise<string | null>;
  clear: () => void;
} {
  const [context, setContext] = useState<PageContext | null>(null);

  useEffect(() => {
    void getPageContext().then(setContext);
    return onMessage(msg => {
      if (msg.type === 'CONTEXT_UPDATED') setContext(msg.context);
    });
  }, []);

  const capture = useCallback(async (): Promise<string | null> => {
    const res = await sendMessage<{ ok: boolean; error?: string }>({ type: 'CAPTURE_PAGE' });
    return res?.ok ? null : (res?.error ?? 'Capture failed');
  }, []);

  const clear = useCallback(() => { void sendMessage({ type: 'CLEAR_CONTEXT' }); }, []);

  return { context, capture, clear };
}

export function useSessionOverrides(): SessionOverrides {
  const [overrides, setOverrides] = useState<SessionOverrides>({});
  useEffect(() => {
    void getOverrides().then(setOverrides);
    const listener = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === 'session' && changes.xoltra_session_overrides) {
        setOverrides((changes.xoltra_session_overrides.newValue as SessionOverrides | undefined) ?? {});
      }
    };
    chrome.storage.onChanged.addListener(listener);
    return () => chrome.storage.onChanged.removeListener(listener);
  }, []);
  return overrides;
}

export function useWorkflows(enabled: boolean): {
  workflows: WorkflowSummary[];
  loading: boolean;
  error: string | null;
  reload: () => void;
} {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    if (!enabled) return;
    setLoading(true);
    getWorkflows()
      .then(r => { setWorkflows(r.workflows || []); setError(null); })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, [enabled]);

  useEffect(() => { reload(); }, [reload]);

  return { workflows, loading, error, reload };
}
