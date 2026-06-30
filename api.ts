const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000';
export async function fetchApi(endpoint: string, options: RequestInit = {}) {
  const url = `${API_URL}${endpoint}`;
  
  const defaultHeaders = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  const response = await fetch(url, {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  });
  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`API Error: ${response.status} - ${errorBody}`);
  }
  return response.json();
}
// System endpoints
export const getStatus = () => fetchApi('/status');
// Tasks
export const getTasks = () => fetchApi('/tasks');
export const createTask = (data: any) => fetchApi('/tasks', { method: 'POST', body: JSON.stringify(data) });
export const cancelTask = (id: string) => fetchApi(`/tasks/${id}`, { method: 'DELETE' });
// Workflows
export const getWorkflows = () => fetchApi('/workflows');
export const getWorkflow = (id: string) => fetchApi(`/workflows/${id}`);
export const runWorkflow = (id: string) => fetchApi(`/workflows/${id}/run`, { method: 'POST' });
// Agents
export const agentAction = (action: 'start' | 'pause' | 'resume' | 'stop') => fetchApi(`/agent/${action}`, { method: 'POST' });
// Permissions
export const grantPermission = (connectorId: string) => fetchApi('/permissions/grant', { method: 'POST', body: JSON.stringify({ connectorId }) });
export const revokePermission = (connectorId: string) => fetchApi('/permissions/revoke', { method: 'POST', body: JSON.stringify({ connectorId }) });
// Roles
export const getRoles = () => fetchApi('/roles');
