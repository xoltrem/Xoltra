'use client';
import { useEffect, useState } from 'react';
import { Clock, Copy, Check, ChevronDown, ChevronRight, FileDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getWorkflows, getWorkflowRuns, getWorkflowRun, exportRunReport } from '@/lib/api';

function runToMarkdown(run: any, workflowName: string): string {
  const lines = [`# Run: ${workflowName}`, ``, `Status: **${run.status}**  `, `Started: ${run.started_at}  `, `Finished: ${run.finished_at || '-'}`, ``, `## Nodes`];
  for (const [nodeId, r] of Object.entries<any>(run.node_results || {})) {
    lines.push(`### ${nodeId} — ${r.status}`);
    if (r.output) lines.push('```json\n' + JSON.stringify(r.output, null, 2) + '\n```');
    if (r.error) lines.push(`**Error:** ${r.error}`);
    if (r.output?.results?.length) {
      lines.push(`**Sources:**`);
      for (const src of r.output.results) lines.push(`- [${src.title}](${src.link})`);
    }
  }
  if (run.usage) {
    lines.push(`\n## Usage`, `Tokens: ${run.usage.total_tokens ?? '-'}  `, `LLM calls: ${run.usage.llm_calls ?? '-'}`);
  }
  return lines.join('\n');
}

export function RunHistory() {
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [runsByWf, setRunsByWf] = useState<Record<string, any[]>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [copiedRunId, setCopiedRunId] = useState<string | null>(null);

  useEffect(() => {
    getWorkflows().then(r => setWorkflows(r.workflows || [])).catch(() => {});
  }, []);

  const toggle = async (wfId: string) => {
    if (expanded === wfId) { setExpanded(null); return; }
    setExpanded(wfId);
    if (!runsByWf[wfId]) {
      try {
        const r = await getWorkflowRuns(wfId);
        setRunsByWf(prev => ({ ...prev, [wfId]: r.runs || [] }));
      } catch { setRunsByWf(prev => ({ ...prev, [wfId]: [] })); }
    }
  };

  const copyRun = async (wfId: string, runId: string, wfName: string) => {
    try {
      const r = await getWorkflowRun(wfId, runId);
      await navigator.clipboard.writeText(runToMarkdown(r.run, wfName));
      setCopiedRunId(runId);
      setTimeout(() => setCopiedRunId(null), 2000);
    } catch { /* clipboard or fetch failed — non-fatal */ }
  };

  const downloadPdf = async (wfId: string, runId: string) => {
    try {
      const res = await exportRunReport(wfId, runId, 'pdf');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `run-${runId.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* non-fatal */ }
  };

  if (workflows.length === 0) return null;

  return (
    <div className="border border-[var(--color-border-main)] rounded-[var(--radius-global)] divide-y divide-[var(--color-border-main)]">
      {workflows.map(wf => (
        <div key={wf.id}>
          <button onClick={() => toggle(wf.id)} className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-[var(--color-panel-200)]/50">
            {expanded === wf.id ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            {wf.name}
          </button>
          {expanded === wf.id && (
            <div className="pl-6 pb-2 space-y-1">
              {(runsByWf[wf.id] || []).length === 0 && <div className="text-xs text-[var(--color-text-secondary)] py-1">No runs yet.</div>}
              {(runsByWf[wf.id] || []).map(run => (
                <div key={run.run_id} className="flex items-center gap-2 text-xs py-1">
                  <Clock className="w-3 h-3 text-[var(--color-text-secondary)]" />
                  <span className={cn(run.status === 'success' ? "text-[var(--color-success)]" : run.status === 'failed' ? "text-[var(--color-error)]" : "text-[var(--color-warning)]")}>{run.status}</span>
                  <span className="text-[var(--color-text-secondary)]">{new Date(run.started_at).toLocaleString()}</span>
                  <button onClick={() => copyRun(wf.id, run.run_id, wf.name)} className="ml-auto flex items-center gap-1 text-[var(--color-text-secondary)] hover:text-white">
                    {copiedRunId === run.run_id ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    {copiedRunId === run.run_id ? 'Copied' : 'Copy as Markdown'}
                  </button>
                  <button onClick={() => downloadPdf(wf.id, run.run_id)} className="flex items-center gap-1 text-[var(--color-text-secondary)] hover:text-white">
                    <FileDown className="w-3 h-3" /> PDF
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
