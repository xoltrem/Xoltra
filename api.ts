/**
 * api.ts
 *
 * Two backend URLs, primary + fallback, both driven by environment
 * variables (not hardcoded ports) so this works unchanged across:
 *   - local dev        (Flask on 5001, Node agent on 4000)
 *   - any cloud deploy  (Vercel etc — no custom ports, just HTTPS domains)
 *
 * If the primary backend errors or is unreachable, requests automatically
 * retry against the fallback backend before failing.
 *
 * Set these in .env.local (dev) or your host's env var dashboard (prod):
 *   NEXT_PUBLIC_API_URL           -> primary backend
 *   NEXT_PUBLIC_API_URL_FALLBACK  -> fallback backend
 */

const PRIMARY_URL  = process.env.NEXT_PUBLIC_API_URL          || 'http://localhost:5001';
const FALLBACK_URL = process.env.NEXT_PUBLIC_API_URL_FALLBACK || 'http://localhost:4000';

function getToken() {
  try { return localStorage.getItem('xoltra_token'); } catch { return null; }
}

async function tryFetch(base: string, endpoint: string, options: RequestInit) {
  const token = getToken();
  const res = await fetch(`${base}/api${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.success === false) {
    throw new Error(data.error || `API Error: ${res.status}`);
  }
  return data;
}

export async function fetchApi(endpoint: string, options: RequestInit = {}) {
  try {
    return await tryFetch(PRIMARY_URL, endpoint, options);
  } catch (primaryErr) {
    // Primary down or erroring — try the fallback before giving up.
    if (!FALLBACK_URL || FALLBACK_URL === PRIMARY_URL) throw primaryErr;
    try {
      const result = await tryFetch(FALLBACK_URL, endpoint, options);
      console.warn(`[api] Primary backend failed, used fallback for ${endpoint}`);
      return result;
    } catch (fallbackErr) {
      throw primaryErr; // surface the original error, it's usually more informative
    }
  }
}

// ─── Auth (auth.py) ─────────────────────────────────────────────────────────
export const register = (email: string, password: string) =>
  fetchApi('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) });
export const login = (email: string, password: string) =>
  fetchApi('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
export const getMe = () => fetchApi('/auth/me');

// ─── Health / Roles (app.py) ────────────────────────────────────────────────
export const getHealth = () => fetchApi('/health');
export const getRoles = () => fetchApi('/roles');
export const getRole = (roleId: string) => fetchApi(`/roles/${roleId}`);

// ─── Goal Pipeline (app.py) ─────────────────────────────────────────────────
export const clarifyGoal = (goal: string, roleId = 'default') =>
  fetchApi('/clarify', { method: 'POST', body: JSON.stringify({ goal, role_id: roleId }) });
export const runGoal = (goal: string, mode = 'default', answers = {}, roleId = 'default') =>
  fetchApi('/run', { method: 'POST', body: JSON.stringify({ goal, mode, answers, role_id: roleId }) });
export const runDocument = (text: string, roleId = 'default') =>
  fetchApi('/run-document', { method: 'POST', body: JSON.stringify({ text, role_id: roleId }) });
export const askQuestion = (question: string, roleId = 'default') =>
  fetchApi('/qa', { method: 'POST', body: JSON.stringify({ question, role_id: roleId }) });

// ─── Workflow Assistant chat (app.py) ───────────────────────────────────────
export const sendAssistantMessage = (message: string, roleId = 'default') =>
  fetchApi('/workflows/assistant', { method: 'POST', body: JSON.stringify({ message, role_id: roleId }) });

// ─── Workflows CRUD + execution (workflow_routes.py) ────────────────────────
export const getWorkflows = () => fetchApi('/workflows');
export const createWorkflow = (data: any) => fetchApi('/workflows', { method: 'POST', body: JSON.stringify(data) });
export const getWorkflow = (id: string) => fetchApi(`/workflows/${id}`);
export const updateWorkflow = (id: string, data: any) => fetchApi(`/workflows/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteWorkflow = (id: string) => fetchApi(`/workflows/${id}`, { method: 'DELETE' });
export const duplicateWorkflow = (id: string) => fetchApi(`/workflows/${id}/duplicate`, { method: 'POST' });
export const runWorkflow = (id: string, triggerData = {}) =>
  fetchApi(`/workflows/${id}/run`, { method: 'POST', body: JSON.stringify({ trigger_data: triggerData }) });
export const getWorkflowRuns = (id: string) => fetchApi(`/workflows/${id}/runs`);
export const getWorkflowRun = (id: string, runId: string) => fetchApi(`/workflows/${id}/runs/${runId}`);
export const getNodeLibrary = () => fetchApi('/nodes');

// ─── Knowledge (app.py) ──────────────────────────────────────────────────────
export const getStats = () => fetchApi('/stats');
export const getKnowledgeNodes = (type = 'goal') => fetchApi(`/knowledge/nodes?type=${type}`);
export const getKnowledgeNode = (nodeId: string) => fetchApi(`/knowledge/nodes/${nodeId}`);
export const compactSession = (messages: any[], sessionTopic?: string) =>
  fetchApi('/knowledge/compact', { method: 'POST', body: JSON.stringify({ messages, session_topic: sessionTopic }) });
export const getKnowledgeContext = (message: string, mode: 'fast' | 'thinking' = 'fast') =>
  fetchApi('/knowledge/context', { method: 'POST', body: JSON.stringify({ message, mode }) });

// ─── Usage / Subscription (subscription_manager.py) ─────────────────────────
export const getUsageSummary = () => fetchApi('/usage/summary');
export const getPlans = () => fetchApi('/usage/plans');
export const upgradePlan = (planId: string, paymentReference?: string) =>
  fetchApi('/usage/upgrade', { method: 'POST', body: JSON.stringify({ plan_id: planId, payment_reference: paymentReference }) });

// ─── Personalization (personalization.py) ───────────────────────────────────
export const personalizationChat = (message: string) =>
  fetchApi('/personalization/chat', { method: 'POST', body: JSON.stringify({ message }) });
export const getPersonalizationProfile = () => fetchApi('/personalization/profile');
export const updatePersonalizationSettings = (patch: { mode?: string; customPrompt?: string }) =>
  fetchApi('/personalization/settings', { method: 'PUT', body: JSON.stringify(patch) });
export const resetPersonalizationTraits = () => fetchApi('/personalization/traits', { method: 'DELETE' });
export const getPersonalizationHistory = () => fetchApi('/personalization/history');
export const clearPersonalizationHistory = () => fetchApi('/personalization/history', { method: 'DELETE' });
