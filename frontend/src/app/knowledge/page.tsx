'use client';
import { useEffect, useState } from 'react';
import { Zap, Calendar, CreditCard, TrendingUp, ChevronDown, ChevronRight, History, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fetchApi, getKnowledgeNodes, getNodeVersions, rollbackNodeVersion } from '@/lib/api';

interface UsageSummary {
  plan_id: 'free_trial' | 'basic' | 'premium' | 'max';
  plan_label: string;
  price_cents: number;
  overage_allowed: boolean;
  tokens_used: number;
  tokens_limit: number | null;
  tokens_remaining: number | null;
  executions_used: number;
  executions_limit: number | null;
  executions_remaining: number | null;
  overage_tokens: number;
  overage_cost_cents: number;
  trial_ends_at?: string;
  payment_verified?: boolean;
  usage_warning?: { level: 'warning' | 'critical' | 'overage'; pct: number; message: string } | null;
}

const getUsageSummary = () => fetchApi('/usage/summary');

function UsageBar({ used, limit }: { used: number; limit: number | null }) {
  if (limit === null) {
    return <div className="text-xs font-mono text-[var(--color-text-secondary)]">{used.toLocaleString()} tokens used — unmetered</div>;
  }
  const pct = Math.min(100, Math.round((used / limit) * 100));
  const color = pct >= 90 ? 'bg-[var(--color-error)]' : pct >= 80 ? 'bg-[var(--color-warning)]' : 'bg-[var(--color-success)]';
  return (
    <div>
      <div className="h-1.5 w-full rounded-full bg-[var(--color-panel-200)] overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <div className="flex justify-center gap-3 mt-1.5">
        <span className="text-xs font-mono text-[var(--color-text-primary)]">{used.toLocaleString()} / {limit.toLocaleString()}</span>
        <span className={cn("text-xs font-mono", pct >= 90 ? "text-[var(--color-error)]" : pct >= 80 ? "text-[var(--color-warning)]" : "text-[var(--color-text-secondary)]")}>{pct}%</span>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, children }: { icon: any; label: string; children: React.ReactNode }) {
  return (
    <div className="p-4 border border-[var(--color-border-main)] rounded-[var(--radius-global)] bg-[var(--color-panel-100)] flex flex-col items-center text-center">
      <div className="flex items-center justify-center gap-2 mb-3">
        <Icon className="w-3.5 h-3.5 text-[var(--color-text-secondary)]" />
        <span className="text-xs font-medium uppercase tracking-wider text-[var(--color-text-secondary)]">{label}</span>
      </div>
      <div className="w-full">{children}</div>
    </div>
  );
}

const PLAN_STYLE: Record<string, string> = {
  free_trial: 'bg-[var(--color-panel-200)] text-[var(--color-text-secondary)] border-[var(--color-border-main)]',
  basic:      'bg-[var(--color-panel-200)] text-[var(--color-text-secondary)] border-[var(--color-border-main)]',
  premium:    'bg-[var(--color-accent)]/10 text-[var(--color-accent)] border-[var(--color-accent)]/20',
  executive:  'bg-[var(--color-success)]/10 text-[var(--color-success)] border-[var(--color-success)]/20',
};

interface KnowledgeNode {
  id: string;
  type: string;
  content: Record<string, any>;
  created_at: string;
  version?: number;
}

interface NodeVersion {
  version: number;
  content: Record<string, any>;
  created_at: string;
  is_current: boolean;
}

function NodeHistoryPanel({ nodeId, onRolledBack }: { nodeId: string; onRolledBack: () => void }) {
  const [versions, setVersions] = useState<NodeVersion[] | null>(null);
  const [error, setError] = useState('');
  const [rollingBackTo, setRollingBackTo] = useState<number | null>(null);

  useEffect(() => {
    getNodeVersions(nodeId)
      .then(res => setVersions(res.versions))
      .catch(e => setError(e.message));
  }, [nodeId]);

  const handleRollback = async (version: number) => {
    setRollingBackTo(version);
    try {
      await rollbackNodeVersion(nodeId, version);
      const res = await getNodeVersions(nodeId);
      setVersions(res.versions);
      onRolledBack();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRollingBackTo(null);
    }
  };

  if (error) return <div className="px-4 py-3 text-xs text-[var(--color-error)]">{error}</div>;
  if (!versions) return <div className="px-4 py-3 text-xs text-[var(--color-text-secondary)]">Loading history...</div>;
  if (versions.length <= 1) return <div className="px-4 py-3 text-xs text-[var(--color-text-secondary)]">No prior versions — this node hasn't been edited.</div>;

  return (
    <div className="px-4 py-3 space-y-2 bg-[var(--color-panel-200)]/40">
      {versions.map(v => (
        <div key={v.version} className="flex items-center justify-between text-xs py-1.5 px-2 rounded border border-[var(--color-border-main)]">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[var(--color-text-secondary)]">v{v.version}</span>
            {v.is_current && (
              <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--color-accent)]/10 text-[var(--color-accent)]">Current</span>
            )}
            <span className="text-[var(--color-text-secondary)]">{new Date(v.created_at).toLocaleString()}</span>
          </div>
          {!v.is_current && (
            <button
              onClick={() => handleRollback(v.version)}
              disabled={rollingBackTo !== null}
              className="flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-[var(--color-border-main)] text-[var(--color-text-secondary)] hover:text-white hover:border-[var(--color-accent)]/40 transition-colors disabled:opacity-40"
            >
              <RotateCcw className="w-3 h-3" />
              {rollingBackTo === v.version ? 'Restoring...' : 'Restore'}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function KnowledgeNodesSection() {
  const [nodeType, setNodeType] = useState<'goal' | 'workflow'>('goal');
  const [nodes, setNodes] = useState<KnowledgeNode[] | null>(null);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = () => {
    getKnowledgeNodes(nodeType)
      .then(res => setNodes(res.nodes))
      .catch(e => setError(e.message));
  };

  useEffect(() => { setNodes(null); load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [nodeType]);

  const nodeLabel = (n: KnowledgeNode) =>
    n.content?.clarified_goal || n.content?.original_input || n.content?.name || n.id.slice(0, 8);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-[var(--color-text-primary)] flex items-center gap-1.5">
          <History className="w-3.5 h-3.5 text-[var(--color-text-secondary)]" /> Knowledge Nodes
        </h2>
        <div className="flex gap-1 text-[10px]">
          {(['goal', 'workflow'] as const).map(t => (
            <button
              key={t}
              onClick={() => setNodeType(t)}
              className={cn(
                "px-2 py-1 rounded uppercase tracking-wider",
                nodeType === t ? "bg-[var(--color-accent)]/10 text-[var(--color-accent)]" : "text-[var(--color-text-secondary)]"
              )}
            >
              {t}s
            </button>
          ))}
        </div>
      </div>

      {error && <div className="text-xs text-[var(--color-error)]">{error}</div>}
      {!nodes && !error && <div className="text-xs text-[var(--color-text-secondary)]">Loading...</div>}
      {nodes && nodes.length === 0 && (
        <div className="text-xs text-[var(--color-text-secondary)] p-4 border border-dashed border-[var(--color-border-main)] rounded-[var(--radius-global)]">
          No {nodeType} nodes yet.
        </div>
      )}

      {nodes && nodes.length > 0 && (
        <div className="border border-[var(--color-border-main)] rounded-[var(--radius-global)] overflow-hidden divide-y divide-[var(--color-border-main)]">
          {nodes.map(n => (
            <div key={n.id}>
              <button
                onClick={() => setExpanded(expanded === n.id ? null : n.id)}
                className="w-full flex items-center justify-between px-4 py-2.5 text-xs hover:bg-[var(--color-panel-200)]/40 transition-colors text-left"
              >
                <span className="text-[var(--color-text-primary)] truncate pr-3">{nodeLabel(n)}</span>
                <span className="flex items-center gap-2 shrink-0 text-[var(--color-text-secondary)]">
                  {n.version ? `v${n.version}` : ''}
                  {expanded === n.id ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                </span>
              </button>
              {expanded === n.id && <NodeHistoryPanel nodeId={n.id} onRolledBack={load} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function KnowledgePage() {
  const [stats, setStats] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getUsageSummary()
      .then(res => setStats(res.summary))
      .catch(e => setError(e.message));
  }, []);

  if (error) return <div className="p-6 text-sm text-[var(--color-error)]">{error}</div>;
  if (!stats) return <div className="p-6 text-sm text-[var(--color-text-secondary)]">Loading usage...</div>;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold mb-1 tracking-tight">Knowledge</h1>
          <p className="text-[var(--color-text-secondary)] text-sm">Token usage and plan limits for this workspace.</p>
        </div>
        <a href="/pricing" className={cn("text-[10px] font-mono px-2 py-1 rounded border uppercase tracking-wider hover:opacity-80 transition-opacity", PLAN_STYLE[stats.plan_id])}>
          {stats.plan_label}
        </a>
      </div>

      {stats.usage_warning && (
        <div className={cn(
          "p-3 rounded-[var(--radius-global)] border text-xs",
          stats.usage_warning.level === 'critical'
            ? "border-[var(--color-error)]/30 bg-[var(--color-error)]/10 text-[var(--color-error)]"
            : "border-[var(--color-warning)]/30 bg-[var(--color-warning)]/10 text-[var(--color-warning)]"
        )}>
          {stats.usage_warning.message}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <StatCard icon={Zap} label="Tokens This Week">
          <UsageBar used={stats.tokens_used} limit={stats.tokens_limit} />
        </StatCard>
        <StatCard icon={Calendar} label="Executions This Week">
          <UsageBar used={stats.executions_used} limit={stats.executions_limit} />
        </StatCard>
      </div>

      {stats.overage_tokens > 0 ? (
        <StatCard icon={CreditCard} label="Overage This Week (pay-as-you-go, not yet billed)">
          <div className="flex items-baseline justify-between">
            <div>
              <div className="text-2xl font-mono font-semibold text-[var(--color-text-primary)]">
                ${(stats.overage_cost_cents / 100).toFixed(2)}
              </div>
              <div className="text-xs text-[var(--color-text-secondary)] mt-1">Tracked only — billing isn't connected yet</div>
            </div>
            <div className="text-right">
              <div className="text-xs font-mono text-[var(--color-text-secondary)]">{stats.overage_tokens.toLocaleString()} overage tokens</div>
            </div>
          </div>
        </StatCard>
      ) : !stats.overage_allowed ? (
        <div className="p-4 border border-dashed border-[var(--color-border-main)] rounded-[var(--radius-global)] flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-[var(--color-text-primary)] flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-[var(--color-accent)]" /> Need higher limits?
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] mt-1">
              {stats.plan_id === 'free_trial' && "Upgrade to Basic, Premium, or Max for higher weekly limits."}
              {stats.plan_id === 'basic' && "Upgrade to Premium or Max for full agent access and pay-as-you-go overage."}
            </p>
          </div>
        </div>
      ) : null}

      {stats.trial_ends_at && stats.plan_id === 'free_trial' && (
        <p className="text-xs text-[var(--color-text-secondary)]">Trial ends {new Date(stats.trial_ends_at).toLocaleDateString()}</p>
      )}

      <KnowledgeNodesSection />
    </div>
  );
}
