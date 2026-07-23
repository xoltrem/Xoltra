/**
 * types.ts — shared domain types for the Companion Extension.
 *
 * These mirror the backend's persisted shapes (backend/workflow_store.py,
 * workflow_engine.py, node_library.py) and the frontend's workflow-graph.ts.
 * If the backend schema changes, change it here in one place.
 */

// ─── Workflow graph (backend shape) ──────────────────────────────────────────

export interface BackendNode {
  id: string;
  /** Node-library type, e.g. "trigger.webhook", "ai.web_search". */
  type: string;
  label: string;
  params: Record<string, unknown>;
  position: { x: number; y: number };
  is_ai_generated?: boolean;
}

export interface BackendEdge {
  id: string;
  source: string;
  target: string;
  source_port?: string | null;
  target_port?: string | null;
}

export interface WorkflowGraph {
  nodes: BackendNode[];
  edges: BackendEdge[];
}

export interface WorkflowSummary {
  id: string;
  name: string;
  status: 'draft' | 'published';
  created_at: string;
  updated_at: string;
  graph: WorkflowGraph;
}

export interface RunSummary {
  run_id: string;
  status: 'success' | 'failed' | 'running' | string;
  started_at: string;
  finished_at: string | null;
}

export interface NodeResult {
  status: string;
  output?: Record<string, unknown>;
  error?: string;
}

export interface RunDetail extends RunSummary {
  node_results?: Record<string, NodeResult>;
  usage?: { total_tokens?: number; llm_calls?: number };
}

export interface AssistantResponse {
  reply: string;
  proposed_node?: { label: string; category: string; actions: string[] } | null;
}

// ─── Session overrides ───────────────────────────────────────────────────────

/**
 * Session-only parameter overrides, keyed workflowId -> nodeId -> paramKey.
 * Stored in chrome.storage.session so they die with the browser session by
 * construction — "session-only" is enforced by the storage tier, not by code
 * that remembers to clean up.
 */
export type ParamOverrides = Record<string, Record<string, unknown>>;
export type SessionOverrides = Record<string, ParamOverrides>;

// ─── Page context (what the content script captures) ─────────────────────────

export interface PageContext {
  url: string;
  title: string;
  /** User's current text selection, if any. */
  selection: string;
  description: string;
  /** Visible h1/h2/h3 texts, capped. */
  headings: string[];
  /** Main readable text excerpt, capped to keep payloads small. */
  excerpt: string;
  /** Lightweight DOM stats — lets the AI reason about the page shape. */
  stats: { links: number; forms: number; images: number; words: number };
  capturedAt: string;
}

// ─── Extension settings ──────────────────────────────────────────────────────

export interface Settings {
  primaryUrl: string;
  fallbackUrl: string;
  /** The Xoltra web app — used for "Open in editor" deep links. */
  webAppUrl: string;
}

export const DEFAULT_SETTINGS: Settings = {
  // Mirrors frontend/src/lib/api.ts defaults.
  primaryUrl: 'http://localhost:5001',
  fallbackUrl: 'http://localhost:10000',
  webAppUrl: 'http://localhost:3000',
};
