/**
 * RunsView — execution inspector. Pick a workflow, see its runs, expand a run
 * for per-node results. When the panel just launched a run, that run is
 * auto-selected so "Run" flows straight into inspection.
 */
import { useCallback, useEffect, useState } from 'react';
import { friendlyError, getWorkflowRun, getWorkflowRuns } from '../../shared/api';
import type { RunDetail, RunSummary, WorkflowSummary } from '../../shared/types';

interface RunsViewProps {
  workflows: WorkflowSummary[];
  /** Pre-selected by App when a run just finished from the Workflows tab. */
  focus: { workflowId: string; runId: string | null } | null;
}

export function RunsView({ workflows, focus }: RunsViewProps) {
  const [workflowId, setWorkflowId] = useState(focus?.workflowId ?? workflows[0]?.id ?? '');
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openRunId, setOpenRunId] = useState<string | null>(focus?.runId ?? null);
  const [details, setDetails] = useState<Record<string, RunDetail>>({});

  const load = useCallback((wfId: string) => {
    if (!wfId) return;
    setLoading(true);
    setError(null);
    getWorkflowRuns(wfId)
      .then(r => setRuns(r.runs || []))
      .catch((e: unknown) => setError(friendlyError(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(workflowId); }, [workflowId, load]);

  // Follow focus changes from the App (a run just finished elsewhere).
  useEffect(() => {
    if (focus) {
      setWorkflowId(focus.workflowId);
      setOpenRunId(focus.runId);
    }
  }, [focus]);

  const toggleRun = async (runId: string) => {
    if (openRunId === runId) { setOpenRunId(null); return; }
    setOpenRunId(runId);
    if (!details[runId]) {
      try {
        const r = await getWorkflowRun(workflowId, runId);
        if (r.run) setDetails(prev => ({ ...prev, [runId]: r.run }));
      } catch { /* detail fetch is best-effort; summary row already shows status */ }
    }
  };

  if (workflows.length === 0) return <div className="empty">No workflows to inspect yet.</div>;

  return (
    <div className="col" style={{ gap: 8 }}>
      <select className="input" value={workflowId} onChange={e => { setWorkflowId(e.target.value); setOpenRunId(null); }} aria-label="Workflow">
        {workflows.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
      </select>

      {loading && <div className="empty"><span className="spinner" style={{ margin: '0 auto' }} /></div>}
      {error && <div className="error-box">{error}</div>}
      {!loading && !error && runs.length === 0 && <div className="empty">No runs yet for this workflow.</div>}

      {runs.map(run => (
        <div key={run.run_id} className="card" style={{ padding: 8 }}>
          <button
            className="btn btn-ghost row spread"
            style={{ width: '100%', padding: '2px 4px' }}
            onClick={() => toggleRun(run.run_id)}
            aria-expanded={openRunId === run.run_id}
          >
            <span className={`small status-${run.status}`} style={{ fontWeight: 600 }}>{run.status}</span>
            <span className="tiny muted">{new Date(run.started_at).toLocaleString()}</span>
          </button>
          {openRunId === run.run_id && (
            <RunDetailView detail={details[run.run_id]} />
          )}
        </div>
      ))}
    </div>
  );
}

function RunDetailView({ detail }: { detail?: RunDetail }) {
  if (!detail) return <div className="row small muted" style={{ padding: 6 }}><span className="spinner" /> Loading…</div>;
  const nodeEntries = Object.entries(detail.node_results ?? {});
  return (
    <div className="col" style={{ gap: 6, paddingTop: 6 }}>
      {nodeEntries.length === 0 && <div className="tiny muted">No node results recorded.</div>}
      {nodeEntries.map(([nodeId, r]) => (
        <div key={nodeId}>
          <div className="row small">
            <span className={`status-${r.status}`}>●</span>
            <span className="mono truncate">{nodeId.slice(0, 8)}</span>
            <span className="muted">{r.status}</span>
          </div>
          {r.error && <div className="error-box tiny" style={{ marginTop: 4 }}>{r.error}</div>}
          {r.output && Object.keys(r.output).length > 0 && (
            <pre className="output">{JSON.stringify(r.output, null, 2).slice(0, 2000)}</pre>
          )}
        </div>
      ))}
      {detail.usage && (
        <div className="tiny muted">
          {detail.usage.total_tokens != null && <>tokens {detail.usage.total_tokens} · </>}
          {detail.usage.llm_calls != null && <>LLM calls {detail.usage.llm_calls}</>}
        </div>
      )}
    </div>
  );
}
