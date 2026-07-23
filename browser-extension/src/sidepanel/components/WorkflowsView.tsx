/**
 * WorkflowsView — list, search, run (with page context + session overrides),
 * and the session override editor. Permanent edits deep-link to the web
 * editor; the extension deliberately does not duplicate the canvas.
 */
import { useMemo, useState } from 'react';
import { friendlyError, runWorkflow } from '../../shared/api';
import { setWorkflowOverrides } from '../../shared/storage';
import type { PageContext, RunDetail, SessionOverrides, WorkflowSummary } from '../../shared/types';

interface WorkflowsViewProps {
  workflows: WorkflowSummary[];
  loading: boolean;
  error: string | null;
  overrides: SessionOverrides;
  pageContext: PageContext | null;
  webAppUrl: string;
  onRunFinished: (workflowId: string, run: RunDetail | null, error?: string) => void;
}

export function WorkflowsView({
  workflows, loading, error, overrides, pageContext, webAppUrl, onRunFinished,
}: WorkflowsViewProps) {
  const [query, setQuery] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? workflows.filter(w => w.name.toLowerCase().includes(q)) : workflows;
  }, [workflows, query]);

  const run = async (wf: WorkflowSummary) => {
    if (runningId) return;
    setRunningId(wf.id);
    setRunError(null);
    try {
      // Captured page context rides in as trigger_data so trigger nodes (and
      // AI nodes downstream) can use what the user is looking at.
      const triggerData = pageContext ? { page_context: pageContext } : {};
      const r = await runWorkflow(wf.id, triggerData, overrides[wf.id]);
      onRunFinished(wf.id, r.run ?? null);
    } catch (e: unknown) {
      const msg = friendlyError(e);
      setRunError(msg);
      onRunFinished(wf.id, null, msg);
    } finally {
      setRunningId(null);
    }
  };

  if (loading) return <div className="empty"><span className="spinner" style={{ margin: '0 auto' }} /></div>;
  if (error) return <div className="error-box">{error}</div>;
  if (workflows.length === 0) {
    return (
      <div className="empty">
        No workflows yet.<br />
        <a className="small" style={{ color: 'var(--color-accent)' }} href={`${webAppUrl}/workflows`} target="_blank" rel="noreferrer">
          Create one in Xoltra →
        </a>
      </div>
    );
  }

  return (
    <div className="col" style={{ gap: 8 }}>
      <input
        className="input"
        placeholder="Search workflows…"
        value={query}
        onChange={e => setQuery(e.target.value)}
        aria-label="Search workflows"
      />
      {runError && <div className="error-box">{runError}</div>}
      {filtered.map(wf => (
        <WorkflowItem
          key={wf.id}
          workflow={wf}
          expanded={expandedId === wf.id}
          onToggle={() => setExpandedId(expandedId === wf.id ? null : wf.id)}
          overridden={Boolean(overrides[wf.id] && Object.keys(overrides[wf.id] ?? {}).length)}
          overrides={overrides[wf.id] ?? {}}
          running={runningId === wf.id}
          anyRunning={runningId !== null}
          webAppUrl={webAppUrl}
          onRun={() => run(wf)}
        />
      ))}
      {filtered.length === 0 && <div className="empty">No match for “{query}”.</div>}
    </div>
  );
}

function WorkflowItem({ workflow: wf, expanded, onToggle, overridden, overrides, running, anyRunning, webAppUrl, onRun }: {
  workflow: WorkflowSummary;
  expanded: boolean;
  onToggle: () => void;
  overridden: boolean;
  overrides: Record<string, Record<string, unknown>>;
  running: boolean;
  anyRunning: boolean;
  webAppUrl: string;
  onRun: () => void;
}) {
  const nodeCount = wf.graph?.nodes?.length ?? 0;
  return (
    <div className="card wf-item col">
      <div className="row spread">
        <button className="btn-ghost btn grow" style={{ justifyContent: 'flex-start', padding: '2px 0' }} onClick={onToggle} aria-expanded={expanded}>
          <span className="truncate" style={{ fontWeight: 500, color: 'var(--color-text-primary)' }}>{wf.name}</span>
        </button>
        <span className={`badge ${wf.status === 'published' ? 'published' : ''}`}>{wf.status}</span>
        {overridden && <span className="badge overridden" title="Session overrides active — cleared when the browser closes">overridden</span>}
      </div>
      <div className="row spread">
        <span className="tiny muted">{nodeCount} node{nodeCount === 1 ? '' : 's'}</span>
        <div className="row" style={{ gap: 6 }}>
          <a className="btn btn-ghost small" href={`${webAppUrl}/workflows/${wf.id}`} target="_blank" rel="noreferrer" title="Permanent editing happens in the full editor">
            Edit
          </a>
          <button className="btn btn-primary" onClick={onRun} disabled={anyRunning} aria-label={`Run ${wf.name}`}>
            {running ? <span className="spinner" /> : '▶'} Run
          </button>
        </div>
      </div>
      {expanded && <OverridesEditor workflow={wf} overrides={overrides} />}
    </div>
  );
}

/**
 * Session override editor: pick a node, pick one of its params, type a value.
 * Values are JSON-parsed when possible ("5" -> 5, "true" -> true) so numeric
 * and boolean params round-trip correctly; anything unparsable stays a string.
 */
function OverridesEditor({ workflow, overrides }: {
  workflow: WorkflowSummary;
  overrides: Record<string, Record<string, unknown>>;
}) {
  const nodes = workflow.graph?.nodes ?? [];
  const [nodeId, setNodeId] = useState(nodes[0]?.id ?? '');
  const [paramKey, setParamKey] = useState('');
  const [value, setValue] = useState('');

  const selectedNode = nodes.find(n => n.id === nodeId);
  const knownParams = selectedNode ? Object.keys(selectedNode.params || {}) : [];

  const add = async () => {
    if (!nodeId || !paramKey.trim()) return;
    let parsed: unknown = value;
    try { parsed = JSON.parse(value); } catch { /* keep as string */ }
    const next = { ...overrides, [nodeId]: { ...overrides[nodeId], [paramKey.trim()]: parsed } };
    await setWorkflowOverrides(workflow.id, next);
    setParamKey('');
    setValue('');
  };

  const remove = async (nid: string, key: string) => {
    const forNode = { ...overrides[nid] };
    delete forNode[key];
    const next = { ...overrides, [nid]: forNode };
    if (Object.keys(forNode).length === 0) delete next[nid];
    await setWorkflowOverrides(workflow.id, Object.keys(next).length ? next : null);
  };

  return (
    <div className="col" style={{ gap: 6, borderTop: '1px solid var(--color-border-main)', paddingTop: 8 }}>
      <div className="tiny muted" style={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        Session overrides — this browser session only
      </div>

      {Object.entries(overrides).map(([nid, params]) =>
        Object.entries(params).map(([k, v]) => {
          const n = nodes.find(x => x.id === nid);
          return (
            <div key={`${nid}.${k}`} className="row spread small">
              <span className="truncate">
                <span className="muted">{n?.label ?? nid.slice(0, 8)} · </span>
                <span className="mono">{k}</span>
                <span className="muted"> = </span>
                <span className="mono">{JSON.stringify(v)}</span>
              </span>
              <button className="btn btn-ghost tiny" onClick={() => remove(nid, k)} aria-label={`Remove override ${k}`}>✕</button>
            </div>
          );
        }),
      )}

      {nodes.length === 0 ? (
        <div className="tiny muted">Empty workflow — nothing to override.</div>
      ) : (
        <>
          <div className="override-row">
            <select className="input" value={nodeId} onChange={e => setNodeId(e.target.value)} aria-label="Node">
              {nodes.map(n => <option key={n.id} value={n.id}>{n.label || n.type}</option>)}
            </select>
            <input
              className="input mono"
              list={`params-${workflow.id}`}
              placeholder="param"
              value={paramKey}
              onChange={e => setParamKey(e.target.value)}
              aria-label="Parameter name"
            />
            <datalist id={`params-${workflow.id}`}>
              {knownParams.map(k => <option key={k} value={k} />)}
            </datalist>
            <span />
          </div>
          <div className="row">
            <input
              className="input mono grow"
              placeholder="value (JSON or text)"
              value={value}
              onChange={e => setValue(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') void add(); }}
              aria-label="Override value"
            />
            <button className="btn" onClick={add} disabled={!paramKey.trim()}>Add</button>
          </div>
        </>
      )}
    </div>
  );
}
