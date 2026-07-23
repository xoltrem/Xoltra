import { fetchApi } from './api';

const PRIMARY_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001';

export interface Project {
  id: string;
  name: string;
  goals: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectSource {
  id: string;
  type: 'github' | 'upload';
  ref: string;
  status: 'pending' | 'indexed' | 'error';
  file_count: number;
  created_at: string;
}

export interface ProjectCache {
  structure_summary: string;
  key_docs_summary: string;
  updated_at: string;
}

export interface ConversationDigest {
  conversation_id?: string;
  summary: string;
  created_at: string;
}

export interface BootstrapPayload {
  project: { id: string; name: string; goals: string };
  structure_summary: string;
  key_docs_summary: string;
  conversation_digests: ConversationDigest[];
  retrieved_chunks: { id: string; text: string; meta: Record<string, any> }[];
}

export const createProject = (name: string, goals?: string) =>
  fetchApi('/projects', { method: 'POST', body: JSON.stringify({ name, goals }) });

export const listProjects = (): Promise<{ projects: Project[] }> => fetchApi('/projects');

export const getProject = (
  id: string
): Promise<{ project: Project; sources: ProjectSource[]; cache: ProjectCache | null }> =>
  fetchApi(`/projects/${id}`);

export const deleteProject = (id: string) => fetchApi(`/projects/${id}`, { method: 'DELETE' });

export const addGithubSource = (projectId: string, repoUrl: string) =>
  fetchApi(`/projects/${projectId}/sources/github`, {
    method: 'POST',
    body: JSON.stringify({ repo_url: repoUrl }),
  });

export async function addUploadSource(projectId: string, files: FileList) {
  const token = (() => {
    try { return localStorage.getItem('xoltra_token'); } catch { return null; }
  })();
  const form = new FormData();
  Array.from(files).forEach(f => form.append('files', f));
  const res = await fetch(`${PRIMARY_URL}/api/projects/${projectId}/sources/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.success === false) throw new Error(data.error || `Upload failed (${res.status})`);
  return data;
}

export const bootstrapProjectSession = (projectId: string, query?: string): Promise<BootstrapPayload> =>
  fetchApi(`/projects/${projectId}/bootstrap${query ? `?query=${encodeURIComponent(query)}` : ''}`);

export const appendProjectDigest = (projectId: string, summary: string, conversationId?: string) =>
  fetchApi(`/projects/${projectId}/digest`, {
    method: 'POST',
    body: JSON.stringify({ summary, conversation_id: conversationId }),
  });
