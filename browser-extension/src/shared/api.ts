/**
 * api.ts — typed Xoltra backend client for the extension.
 *
 * Mirrors frontend/src/lib/api.ts semantics: primary URL with automatic
 * fallback, Bearer JWT, `{ success: false, error }` body convention. Runs in
 * the service worker and extension pages; host_permissions in the manifest
 * exempt these fetches from CORS, so the Flask backend needs no changes.
 */
import { getSettings } from './storage';
import { getToken } from './storage';
import type {
  AssistantResponse, ParamOverrides, RunDetail, RunSummary, WorkflowSummary,
} from './types';

/**
 * Error taxonomy (mirrors backend/auth.py + moderation.py behavior):
 *  - 401                       -> token expired/invalid; user must re-login
 *                                 (JWT TTL is 24h, there is no refresh token).
 *  - 403 code TERMS_NOT_ACCEPTED -> ToS gate; accept in the Xoltra web app.
 *  - 403 timeout:true          -> account under a moderation timeout.
 *  - 429                       -> rate limited. NEVER auto-retry: repeated
 *                                 429s feed moderation.record_violation and
 *                                 escalate into account suspensions.
 */
export type ApiErrorKind = 'auth' | 'terms' | 'suspended' | 'rate_limited' | 'http';

export class ApiError extends Error {
  status: number;
  kind: ApiErrorKind;
  constructor(message: string, status: number, kind: ApiErrorKind = 'http') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.kind = kind;
  }
}

function classify(status: number, data: Record<string, unknown>): ApiErrorKind {
  if (status === 401) return 'auth';
  if (status === 403 && data.code === 'TERMS_NOT_ACCEPTED') return 'terms';
  if (status === 403 && data.timeout) return 'suspended';
  if (status === 429) return 'rate_limited';
  return 'http';
}

export function friendlyError(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.kind) {
      case 'auth': return 'Session expired — sign in again in the extension options.';
      case 'terms': return 'Terms of Service not accepted yet — open the Xoltra web app to accept them.';
      case 'suspended': return 'This account is temporarily suspended.';
      case 'rate_limited': return 'Rate limited — wait a moment before trying again.';
    }
  }
  return e instanceof Error ? e.message : 'Something went wrong';
}

async function tryFetch(base: string, endpoint: string, options: RequestInit): Promise<unknown> {
  const token = await getToken();
  const res = await fetch(`${base}/api${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  const data: Record<string, unknown> = await res.json().catch(() => ({}));
  if (!res.ok || data.success === false) {
    throw new ApiError(
      String(data.error || `API error ${res.status}`),
      res.status,
      classify(res.status, data),
    );
  }
  return data;
}

export async function fetchApi<T = Record<string, unknown>>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const { primaryUrl, fallbackUrl } = await getSettings();
  try {
    return (await tryFetch(primaryUrl, endpoint, options)) as T;
  } catch (primaryErr) {
    // 4xx = the backend answered; retrying elsewhere won't change the answer.
    if (primaryErr instanceof ApiError && primaryErr.status >= 400 && primaryErr.status < 500) {
      throw primaryErr;
    }
    if (!fallbackUrl || fallbackUrl === primaryUrl) throw primaryErr;
    try {
      return (await tryFetch(fallbackUrl, endpoint, options)) as T;
    } catch {
      throw primaryErr; // original error is usually more informative
    }
  }
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

// ─── Auth ────────────────────────────────────────────────────────────────────

export const login = (email: string, password: string) =>
  fetchApi<{ token?: string; access_token?: string; user?: unknown }>('/auth/login', post({ email, password }));

export const getMe = () => fetchApi('/auth/me');

// ─── Workflows ───────────────────────────────────────────────────────────────

export const getWorkflows = () => fetchApi<{ workflows: WorkflowSummary[] }>('/workflows');
export const getWorkflow = (id: string) => fetchApi<{ workflow: WorkflowSummary }>(`/workflows/${id}`);

export const runWorkflow = (id: string, triggerData: Record<string, unknown> = {}, paramOverrides?: ParamOverrides) =>
  fetchApi<{ run: RunDetail }>(`/workflows/${id}/run`, post({
    trigger_data: triggerData,
    ...(paramOverrides && Object.keys(paramOverrides).length > 0 ? { param_overrides: paramOverrides } : {}),
  }));

export const getWorkflowRuns = (id: string) =>
  fetchApi<{ runs: RunSummary[] }>(`/workflows/${id}/runs`);

export const getWorkflowRun = (id: string, runId: string) =>
  fetchApi<{ run: RunDetail }>(`/workflows/${id}/runs/${runId}`);

// ─── Assistant ───────────────────────────────────────────────────────────────

export const sendAssistantMessage = (message: string, conversationId: string) =>
  fetchApi<AssistantResponse>('/workflows/assistant', post({
    message,
    role_id: 'default',
    conversation_id: conversationId,
  }));
