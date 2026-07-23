'use client';
import { useState, useRef, useEffect } from 'react';
import { X, Brain, Loader2, CheckCircle2, Send } from 'lucide-react';
import { runGoalStream } from '@/lib/api';
import { notify } from '@/lib/notifications';

interface RunSummaryInfo {
  mode?: string;
  role_id?: string;
  critic_status?: string;
  operator_used?: boolean;
  stages_run?: number;
}

interface ThinkingPanelProps {
  open: boolean;
  onClose: () => void;
}

const STAGE_LABELS: Record<string, string> = {
  router: 'Routing', clarifier: 'Clarifying', architect: 'Architecting',
  critic: 'Reviewing', operator: 'Operating', validator: 'Validating',
  compiler: 'Compiling', qa: 'Answering',
};

function renderOutput(text: string) {
  // Splits on fenced code blocks so code renders monospace/distinct from prose.
  const parts = text.split(/```(\w*)\n([\s\S]*?)```/g);
  const nodes: React.ReactNode[] = [];
  for (let i = 0; i < parts.length; i += 3) {
    if (parts[i]) nodes.push(<p key={i} className="whitespace-pre-wrap">{parts[i]}</p>);
    if (parts[i + 2] !== undefined) {
      nodes.push(
        <pre key={i + 1} className="bg-[#0d0d0d] border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-3 overflow-x-auto text-[11px] font-mono text-[var(--color-text-primary)]">
          <code>{parts[i + 2]}</code>
        </pre>
      );
    }
  }
  return nodes;
}

export function ThinkingPanel({ open, onClose }: ThinkingPanelProps) {
  const [goal, setGoal] = useState('');
  const [stages, setStages] = useState<string[]>([]);
  const [output, setOutput] = useState<string | null>(null);
  const [summary, setSummary] = useState<RunSummaryInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [stages, output]);

  const run = async () => {
    if (!goal.trim() || loading) return;
    setLoading(true);
    setStages([]);
    setOutput(null);
    setSummary(null);
    setError(null);

    try {
      const result = await runGoalStream(goal.trim(), (step) => {
        setStages(prev => [...prev, step]);
      });
      setOutput(result.output || '');
      setSummary({
        mode: result.mode, role_id: result.role_id,
        critic_status: result.critic_status, operator_used: result.operator_used,
        stages_run: (result.output_parsed ? Object.keys(result.output_parsed).length : undefined),
      });
      notify('Xoltra responded', goal.trim().slice(0, 120));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Run failed');
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed right-4 bottom-4 z-40 w-[420px] h-[560px] flex flex-col bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] shadow-2xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--color-border-main)] shrink-0">
        <Brain className="w-4 h-4 text-[var(--color-accent)]" />
        <div className="flex-1">
          <div className="text-sm font-medium text-[var(--color-text-primary)]">Thinking</div>
          <div className="text-[10px] text-[var(--color-text-secondary)]">Live agent stages + code preview</div>
        </div>
        <button onClick={onClose} className="text-[var(--color-text-secondary)] hover:text-white transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {stages.length > 0 && (
          <div className="space-y-1.5">
            {stages.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
                {i === stages.length - 1 && loading
                  ? <Loader2 className="w-3 h-3 animate-spin text-[var(--color-accent)]" />
                  : <CheckCircle2 className="w-3 h-3 text-[var(--color-success)]" />}
                {STAGE_LABELS[s] || s}
              </div>
            ))}
          </div>
        )}

        {error && <div className="text-xs text-[var(--color-error)]">{error}</div>}

        {output !== null && (
          <div className="pt-2 border-t border-[var(--color-border-main)] text-xs text-[var(--color-text-primary)] space-y-2">
            {renderOutput(output)}
          </div>
        )}

        {summary && (
          <div className="p-3 border border-[var(--color-success)]/30 bg-[var(--color-success)]/10 rounded-[var(--radius-global)] text-xs space-y-0.5">
            <div className="flex items-center gap-1.5 text-[var(--color-success)] font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" /> Done
            </div>
            <div className="text-[var(--color-text-secondary)]">
              mode: {summary.mode} · role: {summary.role_id} · critic: {summary.critic_status || 'n/a'}
              {summary.operator_used ? ' · operator used' : ''}
            </div>
          </div>
        )}
      </div>

      <div className="p-3 border-t border-[var(--color-border-main)] shrink-0">
        <div className="flex items-center gap-2">
          <input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && run()}
            placeholder="Describe a goal to run..."
            className="flex-1 bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-accent)]/40"
          />
          <button
            onClick={run}
            disabled={loading || !goal.trim()}
            className="w-8 h-8 shrink-0 flex items-center justify-center rounded-[var(--radius-global)] bg-[var(--color-accent)] text-black disabled:opacity-30 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
