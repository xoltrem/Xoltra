// ─── Projects (projects.py) — append to frontend/src/lib/api.ts ────────────

export const createProject = (name: string, goals?: string) =>
  fetchApi('/projects', { method: 'POST', body: JSON.stringify({ name, goals }) });
export const listProjects = () => fetchApi('/projects');
export const getProject = (id: string) => fetchApi(`/projects/${id}`);
export const deleteProject = (id: string) => fetchApi(`/projects/${id}`, { method: 'DELETE' });

export const addGithubSource = (projectId: string, repoUrl: string) =>
  fetchApi(`/projects/${projectId}/sources/github`, { method: 'POST', body: JSON.stringify({ repo_url: repoUrl }) });

export async function addUploadSource(projectId: string, files: FileList) {
  const token = (() => { try { return localStorage.getItem('xoltra_token'); } catch { return null; } })();
  const form = new FormData();
  Array.from(files).forEach(f => form.append('files', f));
  const PRIMARY_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001';
  const res = await fetch(`${PRIMARY_URL}/api/projects/${projectId}/sources/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.success === false) throw new Error(data.error || `Upload failed (${res.status})`);
  return data;
}

export const bootstrapProjectSession = (projectId: string, query?: string) =>
  fetchApi(`/projects/${projectId}/bootstrap${query ? `?query=${encodeURIComponent(query)}` : ''}`);

export const appendProjectDigest = (projectId: string, summary: string, conversationId?: string) =>
  fetchApi(`/projects/${projectId}/digest`, { method: 'POST', body: JSON.stringify({ summary, conversation_id: conversationId }) });
