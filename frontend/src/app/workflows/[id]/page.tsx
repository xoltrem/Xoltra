'use client';
/**
 * /workflows/[id] — the full Workflow Builder.
 *
 * Architecture notes:
 *  - The zustand useWorkflowCanvasStore is the single source of truth for the
 *    graph. React Flow is a controlled view over it.
 *  - Structural edits (add/remove/connect/paste/layout) go through pushState()
 *    so they're undoable; transient edits (drag positions, selection) go
 *    through setCurrent() and only become a history entry on drag-stop.
 *  - Autosave: any graph change debounces a PUT /api/workflows/<id>.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ReactFlow, ReactFlowProvider, Background, BackgroundVariant, MiniMap, Controls,
  applyNodeChanges, applyEdgeChanges, addEdge, useReactFlow,
  type NodeChange, type EdgeChange, type Connection, type Edge as FlowEdge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  ArrowLeft, Undo2, Redo2, Play, Loader2, Sparkles, Check,
  LayoutGrid, CloudUpload, ChevronDown,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { CustomNode } from '@/components/workflow/CustomNode';
import { NodePalette, PALETTE_DRAG_TYPE } from '@/components/workflow/NodePalette';
import { NodeConfigPanel } from '@/components/workflow/NodeConfigPanel';
import { AIAssistantPanel, type ProposedNodePayload } from '@/components/workflow/AIAssistantPanel';
import { getWorkflow, updateWorkflow, runWorkflow, getNodeLibrary } from '@/lib/api';
import { notify } from '@/lib/notifications';
import { useWorkflowCanvasStore } from '@/stores';
import {
  backendToFlow, flowToBackend, nodeFromDefinition, autoLayout, nextFreePosition,
  categoryOf, newId, GRID_SIZE, CATEGORY_DEFAULT_TYPE,
  type NodeDefinition, type WorkflowFlowNode,
} from '@/lib/workflow-graph';

const nodeTypes = { custom: CustomNode };

const defaultEdgeOptions = {
  style: { stroke: 'var(--color-border-hover)', strokeWidth: 1.5 },
  animated: false,
};

function WorkflowEditor() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const flow = useReactFlow();
  const {
    nodes, edges, pushState, setCurrent, undo, redo, canUndo, canRedo, reset,
  } = useWorkflowCanvasStore();

  const [name, setName] = useState('');
  const [status, setStatus] = useState<'draft' | 'published'>('draft');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'dirty' | 'error'>('saved');
  const [running, setRunning] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [statusMenuOpen, setStatusMenuOpen] = useState(false);
  const [library, setLibrary] = useState<NodeDefinition[]>([]);
  const [libraryFailed, setLibraryFailed] = useState(false);
  // Which node's config panel is open. Selection on canvas drives this.
  const [configNodeId, setConfigNodeId] = useState<string | null>(null);
  const statusMenuRef = useRef<HTMLDivElement>(null);

  // Close status dropdown on outside click.
  useEffect(() => {
    if (!statusMenuOpen) return;
    const close = (e: Event) => {
      if (!statusMenuRef.current?.contains(e.target as Node)) setStatusMenuOpen(false);
    };
    window.addEventListener('mousedown', close);
    return () => window.removeEventListener('mousedown', close);
  }, [statusMenuOpen]);

  const clipboardRef = useRef<{ nodes: WorkflowFlowNode[]; edges: FlowEdge[] } | null>(null);
  const dragSnapshotRef = useRef<{ nodes: WorkflowFlowNode[]; edges: FlowEdge[] } | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedGraphRef = useRef<string>('');
  const loadedRef = useRef(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // ─── Load ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    getWorkflow(id)
      .then(r => {
        if (cancelled) return;
        const wf = r.workflow || r;
        setName(wf.name || 'Untitled Workflow');
        setStatus(wf.status === 'published' ? 'published' : 'draft');
        const { nodes: n, edges: e } = backendToFlow(wf.graph || { nodes: [], edges: [] });
        reset({ nodes: n, edges: e });
        lastSavedGraphRef.current = JSON.stringify(flowToBackend(n, e));
        // Arm autosave AFTER the reset-triggered render, otherwise the act of
        // loading immediately marks the workflow dirty and re-saves it.
        setTimeout(() => { loadedRef.current = true; }, 0);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setLoadError(e instanceof Error ? e.message : 'Failed to load workflow');
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [id, reset]);

  // Node library — fetched once, shared by the palette and the config panel.
  useEffect(() => {
    getNodeLibrary()
      .then(r => setLibrary(r.nodes || []))
      .catch(() => setLibraryFailed(true));
  }, []);

  // ─── Autosave ──────────────────────────────────────────────────────────────
  const scheduleSave = useCallback(() => {
    if (!loadedRef.current) return;
    setSaveState('dirty');
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      const s = useWorkflowCanvasStore.getState();
      const serialized = JSON.stringify(flowToBackend(s.nodes as WorkflowFlowNode[], s.edges));
      // Selection-only / no-op changes: nothing actually persisted differs —
      // skip the network round-trip entirely.
      if (serialized === lastSavedGraphRef.current) {
        setSaveState('saved');
        return;
      }
      setSaveState('saving');
      try {
        await updateWorkflow(id, { graph: JSON.parse(serialized) });
        lastSavedGraphRef.current = serialized;
        setSaveState('saved');
      } catch {
        setSaveState('error');
      }
    }, 1200);
  }, [id]);

  useEffect(() => () => { if (saveTimer.current) clearTimeout(saveTimer.current); }, []);

  // Flush a pending save when the tab/page is being left, so the last edit
  // inside the debounce window isn't silently dropped.
  useEffect(() => {
    const flush = () => {
      if (!loadedRef.current) return;
      const s = useWorkflowCanvasStore.getState();
      const serialized = JSON.stringify(flowToBackend(s.nodes as WorkflowFlowNode[], s.edges));
      if (serialized === lastSavedGraphRef.current) return;
      // Best-effort fire-and-forget; on client-side navigation the request
      // completes normally, on tab close it may be cut short — acceptable
      // since the debounced autosave covers everything older than ~1s.
      updateWorkflow(id, { graph: JSON.parse(serialized) }).catch(() => {});
      lastSavedGraphRef.current = serialized;
    };
    window.addEventListener('pagehide', flush);
    return () => {
      window.removeEventListener('pagehide', flush);
      flush(); // client-side navigation unmount
    };
  }, [id]);

  // Any graph change (including undo/redo) marks dirty + schedules a save.
  useEffect(() => {
    if (loadedRef.current) scheduleSave();
  }, [nodes, edges, scheduleSave]);

  const saveMeta = useCallback(async (patch: { name?: string; status?: string }) => {
    try {
      await updateWorkflow(id, patch);
      setSaveState('saved');
    } catch (e: unknown) {
      notify('Save failed', e instanceof Error ? e.message : 'Unknown error');
    }
  }, [id]);

  // ─── React Flow change handlers ────────────────────────────────────────────
  const onNodesChange = useCallback((changes: NodeChange<WorkflowFlowNode>[]) => {
    const s = useWorkflowCanvasStore.getState();
    const hasRemove = changes.some(c => c.type === 'remove');
    const next = applyNodeChanges(changes, s.nodes as WorkflowFlowNode[]);
    if (hasRemove) {
      // Also drop edges touching removed nodes so we never orphan them.
      const removedIds = new Set(changes.filter(c => c.type === 'remove').map(c => (c as { id: string }).id));
      const nextEdges = s.edges.filter(e => !removedIds.has(e.source) && !removedIds.has(e.target));
      pushState({ nodes: next, edges: nextEdges });
    } else {
      setCurrent({ nodes: next });
    }
  }, [pushState, setCurrent]);

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    const s = useWorkflowCanvasStore.getState();
    const next = applyEdgeChanges(changes, s.edges);
    if (changes.some(c => c.type === 'remove')) {
      pushState({ nodes: s.nodes as WorkflowFlowNode[], edges: next });
    } else {
      setCurrent({ edges: next });
    }
  }, [pushState, setCurrent]);

  const onConnect = useCallback((conn: Connection) => {
    const s = useWorkflowCanvasStore.getState();
    pushState({
      nodes: s.nodes as WorkflowFlowNode[],
      edges: addEdge({ ...conn, id: newId() }, s.edges),
    });
  }, [pushState]);

  // ─── Node configuration ────────────────────────────────────────────────────
  const patchNode = useCallback((nodeId: string, patch: { label?: string; params?: Record<string, unknown> }) => {
    const s = useWorkflowCanvasStore.getState();
    pushState({
      nodes: (s.nodes as WorkflowFlowNode[]).map(n =>
        n.id === nodeId
          ? { ...n, data: { ...n.data, ...(patch.label !== undefined ? { label: patch.label } : {}), ...(patch.params !== undefined ? { params: patch.params } : {}) } }
          : n),
      edges: s.edges,
    });
  }, [pushState]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: WorkflowFlowNode) => {
    setConfigNodeId(node.id);
  }, []);

  const onPaneClick = useCallback(() => setConfigNodeId(null), []);

  // Drag: snapshot at start, single history entry at stop.
  const onNodeDragStart = useCallback(() => {
    const s = useWorkflowCanvasStore.getState();
    dragSnapshotRef.current = { nodes: s.nodes as WorkflowFlowNode[], edges: s.edges };
  }, []);
  const onNodeDragStop = useCallback(() => {
    const snap = dragSnapshotRef.current;
    dragSnapshotRef.current = null;
    if (!snap) return;
    // Positions already live in the store via setCurrent — just record the
    // pre-drag snapshot as one history entry so the whole move is undoable.
    useWorkflowCanvasStore.setState(st => ({
      past: [...st.past, snap].slice(-50),
      future: [],
    }));
  }, []);

  // ─── Adding nodes ──────────────────────────────────────────────────────────
  const addDefinition = useCallback((def: NodeDefinition, position?: { x: number; y: number }) => {
    const s = useWorkflowCanvasStore.getState();
    const currentNodes = s.nodes as WorkflowFlowNode[];
    const pos = position ?? nextFreePosition(currentNodes);
    const node = nodeFromDefinition(def, pos);
    // Convenience: auto-connect from the rightmost existing node when the new
    // node was appended (not dropped at an explicit position).
    const newEdges = [...s.edges];
    if (!position && currentNodes.length > 0 && !def.node_type.startsWith('trigger.')) {
      const rightmost = currentNodes.reduce((a, b) => (a.position.x >= b.position.x ? a : b));
      newEdges.push({ id: newId(), source: rightmost.id, target: node.id });
    }
    pushState({ nodes: [...currentNodes, node], edges: newEdges });
  }, [pushState]);

  const onDrop = useCallback((e: React.DragEvent) => {
    const raw = e.dataTransfer.getData(PALETTE_DRAG_TYPE);
    if (!raw) return;
    e.preventDefault();
    try {
      const def: NodeDefinition = JSON.parse(raw);
      const pos = flow.screenToFlowPosition({ x: e.clientX, y: e.clientY });
      addDefinition(def, pos);
    } catch { /* malformed drag payload — ignore */ }
  }, [flow, addDefinition]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    if (e.dataTransfer.types.includes(PALETTE_DRAG_TYPE)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
    }
  }, []);

  // AI assistant proposals land on the live canvas, auto-positioned and
  // auto-connected to the current chain — dashed border via isAIGenerated.
  const handleAcceptNode = useCallback((proposal: ProposedNodePayload) => {
    const s = useWorkflowCanvasStore.getState();
    const currentNodes = s.nodes as WorkflowFlowNode[];
    const pos = nextFreePosition(currentNodes);
    const category = categoryOf(proposal.category);
    const node: WorkflowFlowNode = {
      id: newId(),
      type: 'custom',
      position: pos,
      data: {
        label: proposal.label,
        category,
        description: proposal.actions.join(' · '),
        action: proposal.category,
        // Concrete library type so the engine can actually execute this node.
        nodeType: CATEGORY_DEFAULT_TYPE[category],
        params: { actions: proposal.actions },
        isAIGenerated: true,
      },
    };
    const newEdges = [...s.edges];
    if (currentNodes.length > 0) {
      const rightmost = currentNodes.reduce((a, b) => (a.position.x >= b.position.x ? a : b));
      newEdges.push({ id: newId(), source: rightmost.id, target: node.id });
    }
    pushState({ nodes: [...currentNodes, node], edges: newEdges });
    // Bring it into view so "Add to Canvas" visibly does something.
    setTimeout(() => flow.fitView({ padding: 0.2, duration: 300 }), 50);
  }, [pushState, flow]);

  // ─── Copy / paste / duplicate ──────────────────────────────────────────────
  const copySelection = useCallback(() => {
    const s = useWorkflowCanvasStore.getState();
    const selected = (s.nodes as WorkflowFlowNode[]).filter(n => n.selected);
    if (selected.length === 0) return false;
    const ids = new Set(selected.map(n => n.id));
    clipboardRef.current = {
      nodes: selected,
      edges: s.edges.filter(e => ids.has(e.source) && ids.has(e.target)),
    };
    return true;
  }, []);

  const paste = useCallback(() => {
    const clip = clipboardRef.current;
    if (!clip || clip.nodes.length === 0) return;
    const s = useWorkflowCanvasStore.getState();
    const idMap = new Map<string, string>();
    const pastedNodes: WorkflowFlowNode[] = clip.nodes.map(n => {
      const nid = newId();
      idMap.set(n.id, nid);
      return {
        ...n,
        id: nid,
        selected: true,
        position: { x: n.position.x + 40, y: n.position.y + 40 },
        data: { ...n.data },
      };
    });
    const pastedEdges: FlowEdge[] = clip.edges.map(e => ({
      ...e,
      id: newId(),
      source: idMap.get(e.source)!,
      target: idMap.get(e.target)!,
    }));
    pushState({
      nodes: [...(s.nodes as WorkflowFlowNode[]).map(n => ({ ...n, selected: false })), ...pastedNodes],
      edges: [...s.edges, ...pastedEdges],
    });
  }, [pushState]);

  // ─── Keyboard shortcuts ────────────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) return;
      if (!(e.ctrlKey || e.metaKey)) return;
      const k = e.key.toLowerCase();
      if (k === 'z' && !e.shiftKey) { e.preventDefault(); undo(); }
      else if (k === 'y' || (k === 'z' && e.shiftKey)) { e.preventDefault(); redo(); }
      else if (k === 'c') { if (copySelection()) e.preventDefault(); }
      else if (k === 'v') { e.preventDefault(); paste(); }
      else if (k === 'd') { e.preventDefault(); if (copySelection()) paste(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [undo, redo, copySelection, paste]);

  // ─── Actions ───────────────────────────────────────────────────────────────
  const handleAutoLayout = useCallback(() => {
    const s = useWorkflowCanvasStore.getState();
    pushState({ nodes: autoLayout(s.nodes as WorkflowFlowNode[], s.edges), edges: s.edges });
    setTimeout(() => flow.fitView({ padding: 0.2, duration: 300 }), 50);
  }, [pushState, flow]);

  const handleRun = useCallback(async () => {
    if (running) return;
    setRunning(true);
    try {
      const r = await runWorkflow(id);
      const runStatus = r.run?.status || r.status || 'started';
      notify('Workflow run finished', `Status: ${runStatus}`);
    } catch (e: unknown) {
      notify('Run failed', e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setRunning(false);
    }
  }, [id, running]);

  const flowNodes = nodes as WorkflowFlowNode[];
  // Derived, not stored: if the configured node was deleted (or undone away),
  // this goes null and the panel closes itself.
  const configNode = useMemo(
    () => (configNodeId ? flowNodes.find(n => n.id === configNodeId) ?? null : null),
    [configNodeId, flowNodes],
  );
  const configDefinition = useMemo(
    () => (configNode ? library.find(d => d.node_type === configNode.data.nodeType) : undefined),
    [configNode, library],
  );
  const saveLabel = useMemo(() => ({
    saved: 'Saved', saving: 'Saving…', dirty: 'Unsaved changes', error: 'Save failed — retrying on next edit',
  })[saveState], [saveState]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-[var(--color-text-secondary)]" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-center p-8">
        <p className="text-sm text-[var(--color-error)]">{loadError}</p>
        <Button variant="outline" size="sm" onClick={() => router.push('/workflows')} className="gap-2">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to workflows
        </Button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--color-border-main)] bg-[var(--color-panel-100)]/60 shrink-0">
        <Button variant="ghost" size="icon" onClick={() => router.push('/workflows')} title="Back to workflows" aria-label="Back to workflows">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          onBlur={() => saveMeta({ name: name.trim() || 'Untitled Workflow' })}
          onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
          aria-label="Workflow name"
          className="bg-transparent text-sm font-medium text-[var(--color-text-primary)] px-2 py-1 rounded-[var(--radius-global)] border border-transparent hover:border-[var(--color-border-main)] focus:border-[var(--color-accent)]/40 focus:outline-none min-w-0 w-[220px]"
        />

        {/* Status toggle */}
        <div className="relative" ref={statusMenuRef}>
          <button
            onClick={() => setStatusMenuOpen(v => !v)}
            className="flex items-center gap-1 text-[10px] uppercase tracking-wider font-medium px-2 py-1 rounded-full border border-[var(--color-border-main)] text-[var(--color-text-secondary)] hover:text-white transition-colors"
          >
            <span className={status === 'published' ? 'text-[var(--color-success)]' : ''}>{status}</span>
            <ChevronDown className="w-3 h-3" />
          </button>
          {statusMenuOpen && (
            <div className="absolute top-full mt-1 left-0 z-50 min-w-[120px] py-1 bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] shadow-2xl text-xs">
              {(['draft', 'published'] as const).map(s => (
                <button
                  key={s}
                  onClick={() => { setStatus(s); setStatusMenuOpen(false); saveMeta({ status: s }); }}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-[var(--color-panel-200)] transition-colors"
                >
                  {status === s ? <Check className="w-3 h-3 text-[var(--color-accent)]" /> : <span className="w-3" />}
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>

        <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-secondary)] ml-1" aria-live="polite">
          {saveState === 'saving' && <Loader2 className="w-3 h-3 animate-spin" />}
          {saveState === 'saved' && <CloudUpload className="w-3 h-3 text-[var(--color-success)]" />}
          {saveLabel}
        </span>

        <div className="flex-1" />

        <Button variant="outline" size="icon" disabled={!canUndo()} onClick={undo} title="Undo (Ctrl+Z)" aria-label="Undo">
          <Undo2 className="w-4 h-4" />
        </Button>
        <Button variant="outline" size="icon" disabled={!canRedo()} onClick={redo} title="Redo (Ctrl+Y)" aria-label="Redo">
          <Redo2 className="w-4 h-4" />
        </Button>
        <Button variant="outline" size="icon" onClick={handleAutoLayout} title="Auto layout" aria-label="Auto layout">
          <LayoutGrid className="w-4 h-4" />
        </Button>
        <Button variant="outline" className="gap-2" onClick={() => setAssistantOpen(true)}>
          <Sparkles className="w-4 h-4 text-[var(--color-accent)]" />
          Assistant
        </Button>
        <Button className="gap-2" onClick={handleRun} disabled={running || flowNodes.length === 0}>
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          Run
        </Button>
      </div>

      {/* Canvas + palette + config */}
      <div className="flex-1 flex min-h-0">
        <NodePalette definitions={library} loadFailed={libraryFailed} onAdd={addDefinition} />
        <div ref={wrapperRef} className="flex-1 relative" onDrop={onDrop} onDragOver={onDragOver}>
          <ReactFlow
            nodes={flowNodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            onNodeDragStart={onNodeDragStart}
            onNodeDragStop={onNodeDragStop}
            defaultEdgeOptions={defaultEdgeOptions}
            snapToGrid
            snapGrid={[GRID_SIZE, GRID_SIZE]}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.1}
            maxZoom={2.5}
            deleteKeyCode={['Delete', 'Backspace']}
            multiSelectionKeyCode={['Shift', 'Control', 'Meta']}
            selectionOnDrag={false}
            proOptions={{ hideAttribution: true }}
            colorMode="dark"
            className="bg-[var(--color-bg-main)]"
          >
            <Background variant={BackgroundVariant.Dots} gap={GRID_SIZE * 2} size={1} color="rgba(255,255,255,0.08)" />
            <MiniMap
              pannable
              zoomable
              className="!bg-[var(--color-panel-100)] !border !border-[var(--color-border-main)] !rounded"
              maskColor="rgba(0,0,0,0.6)"
              nodeColor="var(--color-panel-200)"
              nodeStrokeColor="var(--color-border-hover)"
            />
            <Controls
              className="!bg-[var(--color-panel-100)] !border !border-[var(--color-border-main)] !rounded !shadow-none [&>button]:!bg-transparent [&>button]:!border-[var(--color-border-main)] [&>button]:!text-[var(--color-text-secondary)] [&>button:hover]:!text-white"
              showInteractive={false}
            />
          </ReactFlow>

          {flowNodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center">
                <p className="text-sm text-[var(--color-text-secondary)] mb-1">Empty canvas</p>
                <p className="text-xs text-[var(--color-text-secondary)]/70">
                  Click or drag a node from the palette, or ask the assistant.
                </p>
              </div>
            </div>
          )}
        </div>

        {configNode && (
          <NodeConfigPanel
            node={configNode}
            definition={configDefinition}
            onChange={patchNode}
            onClose={() => setConfigNodeId(null)}
          />
        )}
      </div>

      <AIAssistantPanel
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        onAcceptNode={handleAcceptNode}
      />
    </div>
  );
}

export default function WorkflowEditorPage() {
  return (
    <ReactFlowProvider>
      <WorkflowEditor />
    </ReactFlowProvider>
  );
}
