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
const FALLBACK_URL = process.env.NEXT_PUBLIC_API_URL_FALLBACK || 'http://localhost:10000';

function getToken() {
  try { return localStorage.getItem('xoltra_token'); } catch { return null; }
}

export function hasToken() {
  return Boolean(getToken());
}

export function setToken(token: string) {
  try { localStorage.setItem('xoltra_token', token); } catch { /* private browsing etc — non-fatal */ }
}

export function clearToken() {
  try { localStorage.removeItem('xoltra_token'); } catch { /* noop */ }
}

/** Thrown instead of a plain Error when the account is under a ToS timeout — lets the UI show a dedicated suspended-account screen instead of a generic toast. */
export class AccountTimeoutError extends Error {
  timeoutUntil: string;
  category: string;
  constructor(message: string, timeoutUntil: string, category: string) {
    super(message);
    this.name = 'AccountTimeoutError';
    this.timeoutUntil = timeoutUntil;
    this.category = category;
  }
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
  if (res.status === 403 && data.timeout) {
    throw new AccountTimeoutError(data.error || 'Account temporarily suspended', data.timeout_until, data.category);
  }
  if (!res.ok || data.success === false) {
    throw new Error(data.error || `API Error: ${res.status}`);
  }
  return data;
}

type FallbackListener = () => void;
const _fallbackListeners: FallbackListener[] = [];
export function onFallbackUsed(fn: FallbackListener) {
  _fallbackListeners.push(fn);
  return () => { const i = _fallbackListeners.indexOf(fn); if (i >= 0) _fallbackListeners.splice(i, 1); };
}

type TimeoutListener = (err: AccountTimeoutError) => void;
const _timeoutListeners: TimeoutListener[] = [];
/** Subscribe to be notified the moment any API call reveals the account is under a ToS timeout — used to show a global suspended-account screen. */
export function onAccountTimeout(fn: TimeoutListener) {
  _timeoutListeners.push(fn);
  return () => { const i = _timeoutListeners.indexOf(fn); if (i >= 0) _timeoutListeners.splice(i, 1); };
}

export async function fetchApi(endpoint: string, options: RequestInit = {}) {
  try {
    return await tryFetch(PRIMARY_URL, endpoint, options);
  } catch (primaryErr) {
    if (primaryErr instanceof AccountTimeoutError) {
      _timeoutListeners.forEach(fn => { try { fn(primaryErr); } catch {} });
      throw primaryErr; // account-level, not a backend-availability issue — retrying elsewhere won't help
    }
    // Primary down or erroring — try the fallback before giving up.
    if (!FALLBACK_URL || FALLBACK_URL === PRIMARY_URL) throw primaryErr;
    try {
      const result = await tryFetch(FALLBACK_URL, endpoint, options);
      console.warn(`[api] Primary backend failed, used fallback for ${endpoint}`);
      _fallbackListeners.forEach(fn => { try { fn(); } catch {} });
      return result;
    } catch (fallbackErr) {
      throw primaryErr; // surface the original error, it's usually more informative
    }
  }
}

// ─── Auth (auth.py) ─────────────────────────────────────────────────────────
export const register = (email: string, password: string, ref?: string) =>
  fetchApi('/auth/register', { method: 'POST', body: JSON.stringify({ email, password, ref }) });
export const login = (email: string, password: string) =>
  fetchApi('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
export const getMe = () => fetchApi('/auth/me');
export const getTermsConsent = () => fetchApi('/auth/terms');
export const getReferralStats = () => fetchApi('/referrals/me');

// ─── Teams/Orgs (teams.py) ───────────────────────────────────────────────────
export const getMyOrgs = () => fetchApi('/orgs/me');
export const getOrgMembers = (orgId: string) => fetchApi(`/orgs/${orgId}/members`);
export const createOrgInvite = (orgId: string, role: string) =>
  fetchApi(`/orgs/${orgId}/invites`, { method: 'POST', body: JSON.stringify({ role }) });
export const joinOrg = (code: string) =>
  fetchApi('/orgs/join', { method: 'POST', body: JSON.stringify({ code }) });
export const setMemberRole = (orgId: string, userId: string, role: string) =>
  fetchApi(`/orgs/${orgId}/members/${userId}/role`, { method: 'PATCH', body: JSON.stringify({ role }) });
export const getOrgAuditLog = (orgId: string) => fetchApi(`/orgs/${orgId}/audit-log/export?format=json`);
// CSV isn't JSON, so this bypasses fetchApi/tryFetch (which always calls
// res.json()) the same way exportRunReport already does for file downloads.
export function exportOrgAuditLogCsv(orgId: string) {
  const token = (() => { try { return localStorage.getItem('xoltra_token'); } catch { return null; } })();
  return fetch(`${PRIMARY_URL}/api/orgs/${orgId}/audit-log/export?format=csv`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}
export const setTermsConsent = (decision: 'accepted' | 'rejected') =>
  fetchApi('/auth/terms', { method: 'PUT', body: JSON.stringify({ decision }) });

// ─── Health / Roles (app.py) ────────────────────────────────────────────────
export const getHealth = () => fetchApi('/health');
export const getStatus = () => fetchApi('/health');
// No agent start/pause/stop route exists in app.py yet — stub so the build
// doesn't break on the missing export; wire up once that endpoint exists.
export const agentAction = async (_action: 'start' | 'pause' | 'resume' | 'stop') => {
  throw new Error('Agent lifecycle control is not implemented on the backend yet');
};

// ─── Auth sessions (auth.py) ─────────────────────────────────────────────────
export const getSessions = () => fetchApi('/auth/sessions');

// ─── Admin (admin_routes.py) — requires X-Admin-Key ─────────────────────────
async function adminFetch(endpoint: string, adminKey: string, options: RequestInit = {}) {
  const res = await fetch(`${PRIMARY_URL}/api/admin${endpoint}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-Admin-Key': adminKey, ...options.headers },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.success === false) throw new Error(data.error || `Admin API error (${res.status})`);
  return data;
}
export const getBackupStatus = (adminKey: string) => adminFetch('/backup-status', adminKey);
export const getAdminHealth = (adminKey: string) => adminFetch('/health', adminKey);
export const triggerBackupSnapshot = (adminKey: string) => adminFetch('/backup-snapshot', adminKey, { method: 'POST' });
export const restoreBackup = (adminKey: string) => adminFetch('/restore-backup', adminKey, { method: 'POST', body: JSON.stringify({ confirm: true }) });

// ─── Moderation / ToS timeouts (admin_routes.py) — requires X-Admin-Key ─────
export const getActiveTimeouts = (adminKey: string) => adminFetch('/moderation/active', adminKey);
export const timeoutUser = (adminKey: string, userId: string, reason: string, durationMinutes: number) =>
  adminFetch('/moderation/timeout', adminKey, { method: 'POST', body: JSON.stringify({ user_id: userId, reason, duration_minutes: durationMinutes }) });
export const clearUserTimeout = (adminKey: string, userId: string) =>
  adminFetch('/moderation/clear', adminKey, { method: 'POST', body: JSON.stringify({ user_id: userId }) });

// ─── Audit log (admin_routes.py) — requires X-Admin-Key ─────────────────────
export const getAuditLog = (adminKey: string, limit = 50, userId?: string) =>
  adminFetch(`/audit-log?limit=${limit}${userId ? `&user_id=${encodeURIComponent(userId)}` : ''}`, adminKey);

export const getRoles = () => fetchApi('/roles');
export const getRole = (roleId: string) => fetchApi(`/roles/${roleId}`);

// ─── Goal Pipeline (app.py) ─────────────────────────────────────────────────
export const clarifyGoal = (goal: string, roleId = 'default') =>
  fetchApi('/clarify', { method: 'POST', body: JSON.stringify({ goal, role_id: roleId }) });
export const runGoal = (goal: string, mode = 'default', answers = {}, roleId = 'default', conversationId?: string) =>
  fetchApi('/run', { method: 'POST', body: JSON.stringify({ goal, mode, answers, role_id: roleId, conversation_id: conversationId }) });

/**
 * Streaming counterpart to runGoal() — calls onStep(name) as each pipeline
 * stage (Router, Clarifier, Architect...) starts, then resolves with the
 * same result shape runGoal() returns. Needs fetch + a stream reader (not
 * `new EventSource`) since this is a POST with an auth header.
 */
export async function runGoalStream(
  goal: string,
  onStep: (step: string) => void,
  opts: { mode?: string; answers?: object; roleId?: string; conversationId?: string } = {},
): Promise<any> {
  const { mode = 'default', answers = {}, roleId = 'default', conversationId } = opts;
  const token = getToken();

  const res = await fetch(`${PRIMARY_URL}/api/run/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ goal, mode, answers, role_id: roleId, conversation_id: conversationId }),
  });
  if (!res.ok || !res.body) throw new Error(`Stream request failed (${res.status})`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line; parse whatever full frames we have
    let frameEnd;
    while ((frameEnd = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, frameEnd);
      buffer = buffer.slice(frameEnd + 2);

      const eventLine = frame.split('\n').find(l => l.startsWith('event: '));
      const dataLine  = frame.split('\n').find(l => l.startsWith('data: '));
      if (!eventLine || !dataLine) continue;

      const event = eventLine.slice(7).trim();
      const data  = JSON.parse(dataLine.slice(6));

      if (event === 'step') onStep(data.step);
      else if (event === 'error') throw new Error(data.error);
      else if (event === 'done') return data;
    }
  }
  throw new Error('Stream ended without a result');
}
export const runDocument = (text: string, roleId = 'default') =>
  fetchApi('/run-document', { method: 'POST', body: JSON.stringify({ text, role_id: roleId }) });
export const askQuestion = (question: string, roleId = 'default') =>
  fetchApi('/qa', { method: 'POST', body: JSON.stringify({ question, role_id: roleId }) });

// ─── Workflow Assistant chat (app.py) ───────────────────────────────────────
export const sendAssistantMessage = (message: string, roleId = 'default', conversationId?: string) =>
  fetchApi('/workflows/assistant', { method: 'POST', body: JSON.stringify({ message, role_id: roleId, conversation_id: conversationId }) });

// ─── Workflow Import / Rebuild (workflow_import.py) ─────────────────────────
export const parseWorkflowImport = (sourceText: string, conversationId?: string) =>
  fetchApi('/workflows/import/parse', { method: 'POST', body: JSON.stringify({ source_text: sourceText, conversation_id: conversationId }) });

export const compileImportSteps = (acceptedSteps: any[]) =>
  fetchApi('/workflows/import/compile', { method: 'POST', body: JSON.stringify({ accepted_steps: acceptedSteps }) });

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
export function exportRunReport(workflowId: string, runId: string, format: 'md' | 'pdf' = 'md') {
  const token = (() => { try { return localStorage.getItem('xoltra_token'); } catch { return null; } })();
  return fetch(`${PRIMARY_URL}/api/workflows/${workflowId}/runs/${runId}/report?format=${format}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

// ─── Templates (templates.py) ────────────────────────────────────────────────
export const saveAsTemplate = (workflowId: string, name?: string, category?: string) =>
  fetchApi('/templates', { method: 'POST', body: JSON.stringify({ workflow_id: workflowId, name, category }) });
export const getTemplates = () => fetchApi('/templates');
export const instantiateTemplate = (templateId: string, name?: string) =>
  fetchApi(`/templates/${templateId}/instantiate`, { method: 'POST', body: JSON.stringify({ name }) });
export const deleteTemplate = (templateId: string) => fetchApi(`/templates/${templateId}`, { method: 'DELETE' });

// Marketplace v1 — publish/browse/use public templates. Requires login,
// same as everything else (no unauthenticated public pages yet).
export const setTemplatePublished = (templateId: string, isPublic: boolean) =>
  fetchApi(`/templates/${templateId}/publish`, { method: 'PATCH', body: JSON.stringify({ is_public: isPublic }) });
export const getPublicTemplates = (category?: string, q?: string) => {
  const params = new URLSearchParams();
  if (category) params.set('category', category);
  if (q) params.set('q', q);
  const qs = params.toString();
  return fetchApi(`/templates/public${qs ? `?${qs}` : ''}`);
};
export const useTemplate = (templateId: string, name?: string) =>
  fetchApi(`/templates/${templateId}/use`, { method: 'POST', body: JSON.stringify({ name }) });

// ─── OneDrive cloud backup (onedrive_routes.py) — Premium/Executive ─────────
export const getOneDriveStatus = () => fetchApi('/premium/onedrive/status');
export const connectOneDrive = () => fetchApi('/premium/onedrive/connect');
export const runOneDriveBackup = () => fetchApi('/premium/onedrive/backup', { method: 'POST' });

// ─── Knowledge (app.py) ──────────────────────────────────────────────────────
export const getStats = () => fetchApi('/stats');
export const getKnowledgeNodes = (type = 'goal') => fetchApi(`/knowledge/nodes?type=${type}`);
export const getKnowledgeNode = (nodeId: string) => fetchApi(`/knowledge/nodes/${nodeId}`);
export const getNodeVersions = (nodeId: string) => fetchApi(`/knowledge/nodes/${nodeId}/versions`);
export const rollbackNodeVersion = (nodeId: string, version: number) =>
  fetchApi(`/knowledge/nodes/${nodeId}/rollback`, { method: 'POST', body: JSON.stringify({ version }) });
export const compactSession = (messages: any[], sessionTopic?: string) =>
  fetchApi('/knowledge/compact', { method: 'POST', body: JSON.stringify({ messages, session_topic: sessionTopic }) });
export const getKnowledgeContext = (message: string, mode: 'fast' | 'thinking' = 'fast') =>
  fetchApi('/knowledge/context', { method: 'POST', body: JSON.stringify({ message, mode }) });

// ─── Conversation memory (workflow_routes.py) ────────────────────────────────
// Deletes every knowledge node/edge the AI learned from one chat — wire this
// to a "delete chat" / "clear conversation" action in the UI.
export const deleteConversationMemory = (conversationId: string) =>
  fetchApi(`/conversations/${conversationId}/memory`, { method: 'DELETE' });

// ─── Usage / Subscription (subscription_manager.py) ─────────────────────────
export const getUsageSummary = () => fetchApi('/usage/summary');
export const getPlans = () => fetchApi('/usage/plans');
export const upgradePlan = (planId: string, paymentReference?: string) =>
  fetchApi('/usage/upgrade', { method: 'POST', body: JSON.stringify({ plan_id: planId, payment_reference: paymentReference }) });
export const getExecutionUsage = (executionId: string) => fetchApi(`/usage/executions/${executionId}`);

// ─── Personalization (personalization.py) ───────────────────────────────────
export const personalizationChat = (message: string) =>
  fetchApi('/personalization/chat', { method: 'POST', body: JSON.stringify({ message }) });
export const getPersonalizationProfile = () => fetchApi('/personalization/profile');
export const updatePersonalizationSettings = (patch: { mode?: string; customPrompt?: string }) =>
  fetchApi('/personalization/settings', { method: 'PUT', body: JSON.stringify(patch) });
export const resetPersonalizationTraits = () => fetchApi('/personalization/traits', { method: 'DELETE' });
export const getPersonalizationHistory = () => fetchApi('/personalization/history');
export const clearPersonalizationHistory = () => fetchApi('/personalization/history', { method: 'DELETE' });
