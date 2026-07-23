/**
 * stores/workspace.ts — state for the Autonomous Workspace page.
 * Separate from stores/index.ts so workspace churn never re-renders
 * the rest of the app.
 */
import { create } from 'zustand';
import {
  TreeNode, Patch, AgentStep, Checkpoint,
  getWorkspaceTree, readWorkspaceFile, writeWorkspaceFile,
  listPatches, getPatch, applyPatch, rollbackPatch, listCheckpoints,
  streamWorkspaceAgent, getWorkspaceChanges,
} from '@/lib/workspaceApi';

export interface OpenFile {
  path: string;
  content: string;
  savedContent: string;
  dirty: boolean;
}

export interface LogLine {
  ts: number;
  level: 'info' | 'warn' | 'error' | 'success';
  text: string;
}

interface WorkspaceState {
  tree: TreeNode[];
  treeLoading: boolean;
  openFiles: OpenFile[];
  activePath: string | null;

  patches: Patch[];
  activePatch: Patch | null;
  checkpoints: Checkpoint[];

  agentRunning: boolean;
  agentSteps: AgentStep[];
  logs: LogLine[];
  abortAgent: (() => void) | null;

  fetchTree: () => Promise<void>;
  openFile: (path: string) => Promise<void>;
  closeFile: (path: string) => void;
  setActivePath: (path: string) => void;
  editFile: (path: string, content: string) => void;
  saveFile: (path: string) => Promise<void>;

  fetchPatches: () => Promise<void>;
  fetchCheckpoints: () => Promise<void>;
  openPatch: (id: string) => Promise<void>;
  approvePatch: (id: string) => Promise<void>;
  undoPatch: (id: string) => Promise<void>;
  closePatch: () => void;

  runAgent: (instruction: string) => void;
  stopAgent: () => void;
  log: (level: LogLine['level'], text: string) => void;

  changeRev: number;
  pollChanges: () => Promise<void>;
  startLivePolling: () => () => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  tree: [],
  treeLoading: false,
  openFiles: [],
  activePath: null,
  patches: [],
  activePatch: null,
  checkpoints: [],
  agentRunning: false,
  agentSteps: [],
  logs: [],
  abortAgent: null,

  log: (level, text) =>
    set((s) => ({ logs: [...s.logs.slice(-499), { ts: Date.now(), level, text }] })),

  fetchTree: async () => {
    set({ treeLoading: true });
    try {
      const data = await getWorkspaceTree();
      set({ tree: data.tree, treeLoading: false });
    } catch (e) {
      get().log('error', `Tree load failed: ${(e as Error).message}`);
      set({ treeLoading: false });
    }
  },

  openFile: async (path) => {
    const existing = get().openFiles.find((f) => f.path === path);
    if (existing) { set({ activePath: path }); return; }
    try {
      const data = await readWorkspaceFile(path);
      set((s) => ({
        openFiles: [...s.openFiles, {
          path, content: data.content, savedContent: data.content, dirty: false,
        }],
        activePath: path,
      }));
    } catch (e) {
      get().log('error', `Open failed: ${(e as Error).message}`);
    }
  },

  closeFile: (path) =>
    set((s) => {
      const openFiles = s.openFiles.filter((f) => f.path !== path);
      return {
        openFiles,
        activePath: s.activePath === path
          ? (openFiles[openFiles.length - 1]?.path ?? null)
          : s.activePath,
      };
    }),

  setActivePath: (path) => set({ activePath: path }),

  editFile: (path, content) =>
    set((s) => ({
      openFiles: s.openFiles.map((f) =>
        f.path === path ? { ...f, content, dirty: content !== f.savedContent } : f),
    })),

  saveFile: async (path) => {
    const file = get().openFiles.find((f) => f.path === path);
    if (!file || !file.dirty) return;
    try {
      await writeWorkspaceFile(path, file.content);
      set((s) => ({
        openFiles: s.openFiles.map((f) =>
          f.path === path ? { ...f, savedContent: f.content, dirty: false } : f),
      }));
      get().log('success', `Saved ${path}`);
      get().fetchCheckpoints();
    } catch (e) {
      get().log('error', `Save failed: ${(e as Error).message}`);
    }
  },

  fetchPatches: async () => {
    try {
      const data = await listPatches();
      set({ patches: data.patches });
    } catch { /* backend may not be up yet — non-fatal */ }
  },

  fetchCheckpoints: async () => {
    try {
      const data = await listCheckpoints();
      set({ checkpoints: data.checkpoints });
    } catch { /* non-fatal */ }
  },

  openPatch: async (id) => {
    try {
      const data = await getPatch(id);
      set({ activePatch: data.patch });
    } catch (e) {
      get().log('error', `Patch load failed: ${(e as Error).message}`);
    }
  },

  approvePatch: async (id) => {
    try {
      const data = await applyPatch(id);
      set({ activePatch: data.patch });
      get().log('success', `Patch applied: ${data.patch.title}`);
      await Promise.all([get().fetchTree(), get().fetchPatches(), get().fetchCheckpoints()]);
      // refresh any open files the patch touched
      for (const op of data.patch.operations) {
        const f = get().openFiles.find((x) => x.path === op.path);
        if (f) {
          try {
            const fresh = await readWorkspaceFile(op.path);
            set((s) => ({
              openFiles: s.openFiles.map((x) =>
                x.path === op.path
                  ? { ...x, content: fresh.content, savedContent: fresh.content, dirty: false }
                  : x),
            }));
          } catch { /* file may have been deleted by the patch */ }
        }
      }
    } catch (e) {
      get().log('error', `Apply failed: ${(e as Error).message}`);
    }
  },

  undoPatch: async (id) => {
    try {
      await rollbackPatch(id);
      get().log('warn', `Patch rolled back`);
      await Promise.all([get().fetchTree(), get().fetchPatches(), get().fetchCheckpoints()]);
      set({ activePatch: null });
    } catch (e) {
      get().log('error', `Rollback failed: ${(e as Error).message}`);
    }
  },

  closePatch: () => set({ activePatch: null }),

  runAgent: (instruction) => {
    if (get().agentRunning) return;
    set({ agentRunning: true, agentSteps: [] });
    get().log('info', `Agent: ${instruction}`);
    const abort = streamWorkspaceAgent(instruction, {
      onStep: (step) => {
        set((s) => {
          // collapse repeated updates of the same phase into one entry
          const steps = [...s.agentSteps];
          const last = steps[steps.length - 1];
          if (last && last.step === step.step && !last.done) steps[steps.length - 1] = step;
          else steps.push(step);
          return { agentSteps: steps };
        });
        if (step.detail) get().log(step.error ? 'error' : 'info', `[${step.step}] ${step.detail}`);
      },
      onDone: async ({ patch }) => {
        set({ agentRunning: false, abortAgent: null });
        get().log('success', `Patch proposed: ${patch.title} (${patch.id})`);
        await get().fetchPatches();
        await get().openPatch(patch.id);
      },
      onError: (message) => {
        set({ agentRunning: false, abortAgent: null });
        get().log('error', `Agent failed: ${message}`);
      },
    });
    set({ abortAgent: abort });
  },

  stopAgent: () => {
    get().abortAgent?.();
    set({ agentRunning: false, abortAgent: null });
    get().log('warn', 'Agent stopped by user');
  },

  changeRev: 0,

  pollChanges: async () => {
    try {
      const data = await getWorkspaceChanges(get().changeRev);
      if (data.rev === get().changeRev) return;
      const events = data.events as { kind: string; paths?: string[] }[];
      set({ changeRev: data.rev });
      if (events.length === 0) return;
      // something changed elsewhere (another tab, background task, terminal)
      await Promise.all([get().fetchTree(), get().fetchPatches(), get().fetchCheckpoints()]);
      // reload any open files an event touched (unless locally dirty)
      const touched = new Set(events.flatMap((e) => e.paths ?? []));
      for (const f of get().openFiles) {
        if (!touched.has(f.path) || f.dirty) continue;
        try {
          const fresh = await readWorkspaceFile(f.path);
          set((s) => ({
            openFiles: s.openFiles.map((x) =>
              x.path === f.path
                ? { ...x, content: fresh.content, savedContent: fresh.content }
                : x),
          }));
        } catch { /* deleted since */ }
      }
    } catch { /* backend unreachable — retry on next tick */ }
  },

  startLivePolling: () => {
    const id = window.setInterval(() => { get().pollChanges(); }, 4000);
    return () => window.clearInterval(id);
  },
}));
