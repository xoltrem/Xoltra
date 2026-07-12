import { create } from 'zustand';
import { getStatus } from '@/lib/api';
interface UIState {
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean) => void;
  searchOpen: boolean;
  setSearchOpen: (v: boolean) => void;
}
export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  searchOpen: false,
  setSearchOpen: (v) => set({ searchOpen: v }),
}));
interface SystemState {
  status: any;
  loading: boolean;
  error: string | null;
  fetchStatus: () => Promise<void>;
}
export const useSystemStore = create<SystemState>((set) => ({
  status: null,
  loading: true,
  error: null,
  fetchStatus: async () => {
    try {
      const data = await getStatus();
      set({ status: data, error: null, loading: false });
    } catch (e: any) {
      set({ error: e.message, loading: false });
    }
  }
}));

// ─── Workflow canvas undo/redo ───────────────────────────────────────────────
// Generic history store for the React Flow canvas (nodes/edges). Separate
// from node_versions (backend, rolls back ONE knowledge node's content) —
// this is client-side, whole-graph undo for accidental deletes/edits before
// a save. Canvas component calls pushState() after each user edit.
interface GraphState { nodes: any[]; edges: any[]; }
interface WorkflowCanvasState {
  nodes: any[];
  edges: any[];
  past: GraphState[];
  future: GraphState[];
  pushState: (next: GraphState) => void;
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
  reset: (initial: GraphState) => void;
}
const HISTORY_LIMIT = 50;
export const useWorkflowCanvasStore = create<WorkflowCanvasState>((set, get) => ({
  nodes: [],
  edges: [],
  past: [],
  future: [],
  pushState: (next) => set(s => ({
    past: [...s.past, { nodes: s.nodes, edges: s.edges }].slice(-HISTORY_LIMIT),
    nodes: next.nodes,
    edges: next.edges,
    future: [],
  })),
  undo: () => set(s => {
    if (s.past.length === 0) return s;
    const prev = s.past[s.past.length - 1];
    return {
      past: s.past.slice(0, -1),
      future: [{ nodes: s.nodes, edges: s.edges }, ...s.future],
      nodes: prev.nodes,
      edges: prev.edges,
    };
  }),
  redo: () => set(s => {
    if (s.future.length === 0) return s;
    const next = s.future[0];
    return {
      future: s.future.slice(1),
      past: [...s.past, { nodes: s.nodes, edges: s.edges }],
      nodes: next.nodes,
      edges: next.edges,
    };
  }),
  canUndo: () => get().past.length > 0,
  canRedo: () => get().future.length > 0,
  reset: (initial) => set({ nodes: initial.nodes, edges: initial.edges, past: [], future: [] }),
}));
