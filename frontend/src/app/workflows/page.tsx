'use client';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Workflow, Plus, Sparkles, Brain, Upload, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { AIAssistantPanel } from '@/components/workflow/AIAssistantPanel';
import { ThinkingPanel } from '@/components/workflow/ThinkingPanel';
import { ImportWorkflowModal } from '@/components/workflow/ImportWorkflowModal';
import { RunHistory } from '@/components/workflow/RunHistory';
import { TemplateGallery } from '@/components/workflow/TemplateGallery';
import { WorkflowCard } from '@/components/workflow/WorkflowCard';
import { notify } from '@/lib/notifications';
import {
  getWorkflows, createWorkflow, deleteWorkflow, duplicateWorkflow,
  runWorkflow, getWorkflowRuns,
} from '@/lib/api';
import type { RunSummary, WorkflowSummary } from '@/lib/workflow-graph';
import type { ProposedNodePayload } from '@/components/workflow/AIAssistantPanel';
import { categoryOf, newId, CATEGORY_DEFAULT_TYPE } from '@/lib/workflow-graph';

export default function WorkflowsPage() {
  const router = useRouter();
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [thinkingOpen, setThinkingOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [lastRuns, setLastRuns] = useState<Record<string, RunSummary | null>>({});
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await getWorkflows();
      const list: WorkflowSummary[] = r.workflows || [];
      setWorkflows(list);
      // Last-execution info per card — fire in parallel, tolerate failures.
      const entries = await Promise.all(
        list.map(async (wf) => {
          try {
            const runs = await getWorkflowRuns(wf.id);
            return [wf.id, (runs.runs || [])[0] || null] as const;
          } catch { return [wf.id, null] as const; }
        }),
      );
      setLastRuns(Object.fromEntries(entries));
    } catch {
      // Backend unreachable — leave the empty state visible.
    } finally {
      setLoading(false);
    }
  }, []);

  // Data-fetch-on-mount: every setState inside load() happens after an await,
  // so it can't cascade renders — the lint rule just can't see through async.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load]);

  const open = (id: string) => router.push(`/workflows/${id}`);

  const handleCreate = async () => {
    if (creating) return;
    setCreating(true);
    try {
      const r = await createWorkflow({ name: 'Untitled Workflow', status: 'draft', graph: { nodes: [], edges: [] } });
      open(r.workflow?.id || r.id);
    } catch (e: unknown) {
      notify('Could not create workflow', e instanceof Error ? e.message : 'Unknown error');
      setCreating(false);
    }
  };

  // Assistant used from the dashboard = "create with AI": first accepted node
  // seeds a fresh draft workflow, then we jump straight into the editor where
  // the rest of the conversation continues on the live canvas.
  const handleAcceptNode = async (node: ProposedNodePayload) => {
    try {
      const category = categoryOf(node.category);
      const graph = {
        nodes: [{
          id: newId(),
          // Concrete library type (not "<category>.custom") so the run engine
          // can execute this node without an unknown-type error.
          type: CATEGORY_DEFAULT_TYPE[category],
          label: node.label,
          params: { actions: node.actions },
          position: { x: 80, y: 120 },
          is_ai_generated: true,
        }],
        edges: [],
      };
      const r = await createWorkflow({ name: node.label, status: 'draft', graph });
      notify('Workflow created', `"${node.label}" added — opening the editor.`);
      open(r.workflow?.id || r.id);
    } catch (e: unknown) {
      notify('Could not create workflow', e instanceof Error ? e.message : 'Unknown error');
    }
  };

  const handleRun = async (id: string) => {
    try {
      await runWorkflow(id);
      notify('Workflow run started', 'Check Run History below for results.');
      load();
    } catch (e: unknown) {
      notify('Run failed', e instanceof Error ? e.message : 'Unknown error');
    }
  };

  const handleDuplicate = async (id: string) => {
    try {
      await duplicateWorkflow(id);
      notify('Workflow duplicated', 'A copy was added to your list.');
      load();
    } catch (e: unknown) {
      notify('Duplicate failed', e instanceof Error ? e.message : 'Unknown error');
    }
  };

  const handleDelete = async (id: string) => {
    const wf = workflows.find(w => w.id === id);
    if (!window.confirm(`Delete "${wf?.name || 'this workflow'}"? This cannot be undone.`)) return;
    try {
      await deleteWorkflow(id);
      setWorkflows(prev => prev.filter(w => w.id !== id));
    } catch (e: unknown) {
      notify('Delete failed', e instanceof Error ? e.message : 'Unknown error');
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto flex flex-col min-h-full space-y-6">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-2xl font-semibold mb-1 tracking-tight">Workflows</h1>
          <p className="text-[var(--color-text-secondary)] text-sm">
            Build automations by hand or describe them to the assistant.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" className="gap-2" onClick={() => setThinkingOpen(true)} title="Show live agent thinking + code preview">
            <Brain className="w-4 h-4 text-[var(--color-accent)]" />
            Thinking
          </Button>
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => setImportOpen(true)}
            title="Rebuild an existing Zapier/Make/n8n automation in Xoltra"
          >
            <Upload className="w-4 h-4 text-[var(--color-accent)]" />
            Import
          </Button>
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => setAssistantOpen(true)}
          >
            <Sparkles className="w-4 h-4 text-[var(--color-accent)]" />
            Ask Assistant
          </Button>
          <Button className="gap-2" onClick={handleCreate} disabled={creating}>
            {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Create Workflow
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 animate-spin text-[var(--color-text-secondary)]" />
        </div>
      ) : workflows.length === 0 ? (
        <div className="flex-1 flex items-center justify-center border border-dashed border-[var(--color-border-main)] rounded-[var(--radius-global)] p-12 text-center">
          <div>
            <div className="w-12 h-12 bg-[var(--color-panel-100)] rounded-full flex items-center justify-center mb-4 mx-auto">
              <Workflow className="w-6 h-6 text-[var(--color-text-secondary)]" />
            </div>
            <h3 className="text-sm font-medium mb-1">No workflows yet</h3>
            <p className="text-xs text-[var(--color-text-secondary)] max-w-[280px] mx-auto mb-4">
              Click &quot;Create Workflow&quot; and describe what you want automated — the assistant builds it with you.
            </p>
            <Button size="sm" onClick={() => setAssistantOpen(true)} className="gap-2">
              <Sparkles className="w-3.5 h-3.5" />
              Start with the assistant
            </Button>
            <Button size="sm" variant="outline" onClick={() => setImportOpen(true)} className="gap-2 mt-2">
              <Upload className="w-3.5 h-3.5" />
              Or rebuild one you already have
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {workflows.map(wf => (
            <WorkflowCard
              key={wf.id}
              workflow={wf}
              lastRun={lastRuns[wf.id]}
              onOpen={open}
              onRun={handleRun}
              onDuplicate={handleDuplicate}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      <TemplateGallery onInstantiated={() => { notify('Workflow created', 'Added from your template.'); load(); }} />

      <RunHistory />

      <AIAssistantPanel
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        onAcceptNode={handleAcceptNode}
      />
      <ThinkingPanel open={thinkingOpen} onClose={() => setThinkingOpen(false)} />
      <ImportWorkflowModal open={importOpen} onClose={() => { setImportOpen(false); load(); }} />
    </div>
  );
}
