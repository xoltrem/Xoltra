/**
 * workflow-graph.ts — shared typed graph model for the Workflow Builder.
 *
 * The backend (workflow_store.py / workflow_engine.py) persists graphs as:
 *   nodes: [{ id, type, label, params, position }]           // type = "ai.web_search" etc.
 *   edges: [{ id, source, target, source_port, target_port }]
 *
 * React Flow (@xyflow/react) wants:
 *   nodes: [{ id, type: "custom", position, data }]
 *   edges: [{ id, source, target, sourceHandle, targetHandle }]
 *
 * Everything that crosses that boundary goes through the converters here so
 * the two shapes never leak into components. Keep this file dependency-light —
 * it's imported by the store, the dashboard, and the editor.
 */

import type { Node as FlowNode, Edge as FlowEdge } from '@xyflow/react';

// ─── Backend (persisted) shapes ──────────────────────────────────────────────

export type NodeCategory = 'trigger' | 'ai' | 'logic' | 'integration' | 'utility';

export interface BackendNode {
  id: string;
  /** Node-library type, e.g. "trigger.webhook", "ai.web_search". */
  type: string;
  label: string;
  params: Record<string, unknown>;
  position: { x: number; y: number };
  description?: string;
  /** Set when the node came from the AI assistant — rendered dashed per PRD. */
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

/** GET /api/nodes entry — the palette's source of truth. */
export interface NodeDefinition {
  node_type: string;
  category: NodeCategory;
  label: string;
  description: string;
  inputs: { name: string; type: string }[];
  outputs: { name: string; type: string }[];
}

export interface RunSummary {
  run_id: string;
  status: 'success' | 'failed' | 'running' | string;
  started_at: string;
  finished_at: string | null;
}

// ─── React Flow node data payload (what CustomNode.tsx reads) ────────────────

export interface FlowNodeData extends Record<string, unknown> {
  label: string;
  category: NodeCategory | string;
  description?: string;
  /** Short action line, e.g. the node_type — shown under the label. */
  action?: string;
  nodeType: string;
  params: Record<string, unknown>;
  isAIGenerated?: boolean;
}

export type WorkflowFlowNode = FlowNode<FlowNodeData>;

// ─── Helpers ─────────────────────────────────────────────────────────────────

export const categoryOf = (nodeType: string): NodeCategory => {
  const prefix = nodeType.split('.')[0];
  return (['trigger', 'ai', 'logic', 'integration', 'utility'].includes(prefix)
    ? prefix
    : 'utility') as NodeCategory;
};

export const newId = () => crypto.randomUUID();

/**
 * The assistant proposes nodes by *category*; the execution engine only knows
 * concrete node-library types. Map to a sensible runnable default so accepted
 * AI nodes execute instead of failing with "unknown node type".
 */
export const CATEGORY_DEFAULT_TYPE: Record<NodeCategory, string> = {
  trigger: 'trigger.manual',
  ai: 'ai.cohere_generate',
  logic: 'logic.condition',
  integration: 'integration.http_request',
  utility: 'utility.transform',
};

/** Grid used for snap-to-grid and auto-layout spacing. */
export const GRID_SIZE = 16;
export const NODE_WIDTH = 240;
export const LAYOUT_X_GAP = 300;
export const LAYOUT_Y_GAP = 150;

// ─── Converters ──────────────────────────────────────────────────────────────

export function backendToFlow(graph: WorkflowGraph): {
  nodes: WorkflowFlowNode[];
  edges: FlowEdge[];
} {
  const nodes: WorkflowFlowNode[] = (graph.nodes || []).map((n) => ({
    id: n.id,
    type: 'custom',
    position: n.position || { x: 0, y: 0 },
    data: {
      label: n.label || n.type,
      category: categoryOf(n.type),
      description: n.description,
      action: n.type,
      nodeType: n.type,
      params: n.params || {},
      isAIGenerated: n.is_ai_generated === true,
    },
  }));

  const edges: FlowEdge[] = (graph.edges || []).map((e) => ({
    id: e.id || `${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    sourceHandle: e.source_port ?? undefined,
    targetHandle: e.target_port ?? undefined,
  }));

  return { nodes, edges };
}

export function flowToBackend(nodes: WorkflowFlowNode[], edges: FlowEdge[]): WorkflowGraph {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.data.nodeType,
      label: n.data.label,
      params: n.data.params || {},
      position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
      ...(n.data.description ? { description: n.data.description } : {}),
      ...(n.data.isAIGenerated ? { is_ai_generated: true } : {}),
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      source_port: e.sourceHandle ?? null,
      target_port: e.targetHandle ?? null,
    })),
  };
}

/** Build a canvas node from a palette/library definition. */
export function nodeFromDefinition(
  def: Pick<NodeDefinition, 'node_type' | 'label' | 'description' | 'category'>,
  position: { x: number; y: number },
  extras?: Partial<FlowNodeData>,
): WorkflowFlowNode {
  return {
    id: newId(),
    type: 'custom',
    position,
    data: {
      label: def.label,
      category: def.category ?? categoryOf(def.node_type),
      description: def.description,
      action: def.node_type,
      nodeType: def.node_type,
      params: {},
      ...extras,
    },
  };
}

// ─── Derived card metadata ───────────────────────────────────────────────────

/** First trigger node's label, for the dashboard cards. */
export function triggerLabel(graph: WorkflowGraph | undefined): string | null {
  const t = graph?.nodes?.find((n) => n.type?.startsWith('trigger.'));
  return t ? t.label || t.type : null;
}

/** Human description: stored description of the first node chain, else counts. */
export function describeGraph(graph: WorkflowGraph | undefined): string {
  const nodes = graph?.nodes || [];
  if (nodes.length === 0) return 'Empty workflow — open to start building.';
  const labels = nodes.slice(0, 3).map((n) => n.label || n.type);
  const suffix = nodes.length > 3 ? ` +${nodes.length - 3} more` : '';
  return labels.join(' → ') + suffix;
}

// ─── Auto layout ─────────────────────────────────────────────────────────────

/**
 * Simple layered (left-to-right) layout: BFS depth from source nodes decides
 * the column, order within a column decides the row. Deterministic, no deps —
 * good enough until graphs get complex enough to justify dagre/elk.
 */
export function autoLayout(nodes: WorkflowFlowNode[], edges: FlowEdge[]): WorkflowFlowNode[] {
  if (nodes.length === 0) return nodes;

  const incoming = new Map<string, number>();
  const adjacency = new Map<string, string[]>();
  nodes.forEach((n) => {
    incoming.set(n.id, 0);
    adjacency.set(n.id, []);
  });
  edges.forEach((e) => {
    if (!incoming.has(e.source) || !incoming.has(e.target)) return;
    incoming.set(e.target, (incoming.get(e.target) || 0) + 1);
    adjacency.get(e.source)!.push(e.target);
  });

  // Kahn-style BFS; nodes in cycles (shouldn't happen) fall back to column 0.
  const depth = new Map<string, number>();
  const queue = nodes.filter((n) => (incoming.get(n.id) || 0) === 0).map((n) => n.id);
  queue.forEach((id) => depth.set(id, 0));
  const remaining = new Map(incoming);
  while (queue.length) {
    const id = queue.shift()!;
    for (const next of adjacency.get(id) || []) {
      depth.set(next, Math.max(depth.get(next) ?? 0, (depth.get(id) ?? 0) + 1));
      remaining.set(next, (remaining.get(next) || 1) - 1);
      if ((remaining.get(next) || 0) === 0) queue.push(next);
    }
  }

  const rows = new Map<number, number>(); // column -> next row index
  return nodes.map((n) => {
    const col = depth.get(n.id) ?? 0;
    const row = rows.get(col) ?? 0;
    rows.set(col, row + 1);
    return {
      ...n,
      position: { x: 60 + col * LAYOUT_X_GAP, y: 80 + row * LAYOUT_Y_GAP },
    };
  });
}

/** A free spot to the right of the current graph — for appended nodes. */
export function nextFreePosition(nodes: WorkflowFlowNode[]): { x: number; y: number } {
  if (nodes.length === 0) return { x: 80, y: 120 };
  const rightmost = nodes.reduce((a, b) => (a.position.x >= b.position.x ? a : b));
  return { x: rightmost.position.x + LAYOUT_X_GAP, y: rightmost.position.y };
}
