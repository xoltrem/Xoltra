/**
 * workspaceApi.ts
 *
 * Client for the Autonomous Workspace API (backend/workspace_routes.py).
 * REST calls go through the shared fetchApi (auth + fallback handling);
 * the agent stream uses fetch-based SSE parsing since EventSource can't
 * POST or send Authorization headers.
 */

import { fetchApi } from '@/lib/api';

const PRIMARY_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001';

// ─── Types ──────────────────────────────────────────────────────────────────

export interface TreeNode {
  name: string;
  path: string;
  type: 'dir' | 'file';
  size?: number;
  children?: TreeNode[];
}

export interface PatchOperation {
  type: 'write' | 'delete' | 'move' | 'mkdir';
  path: string;
  to?: string;
  reason?: string;
  intent?: string;
}

export interface PatchDiff { path: string; diff: string; }

export interface Patch {
  id: string;
  title: string;
  created: number;
  status: 'proposed' | 'applied' | 'failed' | 'rolled_back';
  checkpoint_id: string | null;
  operation_count?: number;
  operations: PatchOperation[];
  diffs?: PatchDiff[];
}

export interface SearchResult { path: string; match: string; kind: string; line: number; }
export interface Checkpoint { id: string; label: string; created: number; files: number; }

export interface AgentStep {
  step: 'index' | 'plan' | 'generate' | 'validate' | 'apply';
  detail: string;
  reasoning?: string;
  operations?: PatchOperation[];
  patch_id?: string;
  done?: boolean;
  error?: boolean;
}

export interface TerminalResult {
  command: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  ok: boolean;
}

// ─── Files ──────────────────────────────────────────────────────────────────

export const getWorkspaceTree = () => fetchApi('/workspace/tree');
export const readWorkspaceFile = (path: string) =>
  fetchApi(`/workspace/file?path=${encodeURIComponent(path)}`);
export const writeWorkspaceFile = (path: string, content: string) =>
  fetchApi('/workspace/file', { method: 'POST', body: JSON.stringify({ path, content }) });
export const createWorkspaceFolder = (path: string) =>
  fetchApi('/workspace/mkdir', { method: 'POST', body: JSON.stringify({ path }) });
export const moveWorkspacePath = (path: string, to: string) =>
  fetchApi('/workspace/move', { method: 'POST', body: JSON.stringify({ path, to }) });
export const deleteWorkspacePath = (path: string) =>
  fetchApi('/workspace/delete', { method: 'POST', body: JSON.stringify({ path }) });

// ─── Index / search ─────────────────────────────────────────────────────────

export const rebuildWorkspaceIndex = () => fetchApi('/workspace/index', { method: 'POST' });
export const searchWorkspace = (q: string) =>
  fetchApi(`/workspace/search?q=${encodeURIComponent(q)}`);
export const searchWorkspaceSemantic = (q: string) =>
  fetchApi(`/workspace/search/semantic?q=${encodeURIComponent(q)}`);
export const getWorkspaceGraph = () => fetchApi('/workspace/graph');

// ─── Live updates / background tasks ────────────────────────────────────────

export interface ChangeEvent { rev: number; ts: number; kind: string; paths?: string[]; }
export interface WorkspaceTask {
  id: string; title: string; status: 'queued' | 'running' | 'done' | 'failed';
  created: number; error: string | null;
}

export const getWorkspaceChanges = (since: number) =>
  fetchApi(`/workspace/changes?since=${since}`);
export const listWorkspaceTasks = () => fetchApi('/workspace/tasks');
export const getWorkspaceTask = (id: string) => fetchApi(`/workspace/tasks/${id}`);
export const submitAgentTask = (instruction: string, autoApply = false) =>
  fetchApi('/workspace/agent/tasks', {
    method: 'POST',
    body: JSON.stringify({ instruction, auto_apply: autoApply }),
  });

// ─── Patches / checkpoints ──────────────────────────────────────────────────

export const listPatches = () => fetchApi('/workspace/patches');
export const getPatch = (id: string) => fetchApi(`/workspace/patches/${id}`);
export const applyPatch = (id: string) =>
  fetchApi(`/workspace/patches/${id}/apply`, { method: 'POST' });
export const rollbackPatch = (id: string) =>
  fetchApi(`/workspace/patches/${id}/rollback`, { method: 'POST' });
export const listCheckpoints = () => fetchApi('/workspace/checkpoints');
export const rollbackCheckpoint = (id: string) =>
  fetchApi(`/workspace/checkpoints/${id}/rollback`, { method: 'POST' });

// ─── Terminal / git ─────────────────────────────────────────────────────────

export const runTerminal = (command: string) =>
  fetchApi('/workspace/terminal', { method: 'POST', body: JSON.stringify({ command }) });
export const gitStatus = () => fetchApi('/workspace/git/status');
export const gitCommit = (message: string, paths?: string[]) =>
  fetchApi('/workspace/git/commit', { method: 'POST', body: JSON.stringify({ message, paths }) });
export const gitPush = (remote?: string, branch?: string) =>
  fetchApi('/workspace/git/push', { method: 'POST', body: JSON.stringify({ remote, branch }) });
export const gitPull = () => fetchApi('/workspace/git/pull', { method: 'POST' });

// ─── Agent SSE stream ───────────────────────────────────────────────────────

export interface AgentStreamHandlers {
  onStep: (step: AgentStep) => void;
  onDone: (result: { plan: unknown; patch: Patch }) => void;
  onError: (message: string) => void;
}

/** POST the instruction, parse the SSE response. Returns an abort fn. */
export function streamWorkspaceAgent(
  instruction: string,
  handlers: AgentStreamHandlers,
  autoApply = false,
): () => void {
  const controller = new AbortController();
  const token = (() => {
    try { return localStorage.getItem('xoltra_token'); } catch { return null; }
  })();

  (async () => {
    try {
      const res = await fetch(`${PRIMARY_URL}/api/workspace/agent/stream`, {
        method: 'POST',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ instruction, auto_apply: autoApply }),
      });
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        throw new Error((data as { error?: string }).error || `Stream failed (${res.status})`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // SSE frames are separated by a blank line: "event: X\ndata: {...}\n\n"
      const processFrame = (frame: string) => {
        let event = 'message';
        let data = '';
        for (const line of frame.split('\n')) {
          if (line.startsWith('event: ')) event = line.slice(7).trim();
          else if (line.startsWith('data: ')) data += line.slice(6);
        }
        if (!data) return;
        let payload: unknown;
        try { payload = JSON.parse(data); } catch { return; }
        if (event === 'step') handlers.onStep(payload as AgentStep);
        else if (event === 'done') handlers.onDone(payload as { plan: unknown; patch: Patch });
        else if (event === 'error') handlers.onError((payload as { error: string }).error);
      };

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx: number;
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          processFrame(buffer.slice(0, idx));
          buffer = buffer.slice(idx + 2);
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        handlers.onError((e as Error).message || 'Agent stream failed');
      }
    }
  })();

  return () => controller.abort();
}
