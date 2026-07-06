'use client';
import { useEffect, useState } from 'react';
import { Zap, Calendar, CreditCard, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fetchApi } from '@/lib/api';

interface UsageSummary {
  plan_id: 'free_trial' | 'basic' | 'premium' | 'executive';
  plan_label: string;
  pay_as_you_go: boolean;
  tokens_used: number;
  tokens_limit: number | null;
  tokens_remaining: number | null;
  executions_used: number;
  executions_limit: number | null;
  executions_remaining: number | null;
  cost_per_million_tokens?: number;
  estimated_cost?: number;
  trial_ends_at?: string;
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
        <span className={cn("text-[10px] font-mono px-2 py-1 rounded border uppercase tracking-wider", PLAN_STYLE[stats.plan_id])}>
          {stats.plan_label}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <StatCard icon={Zap} label="Tokens This Month">
          <UsageBar used={stats.tokens_used} limit={stats.tokens_limit} />
        </StatCard>
        <StatCard icon={Calendar} label="Executions This Month">
          <UsageBar used={stats.executions_used} limit={stats.executions_limit} />
        </StatCard>
      </div>

      {stats.pay_as_you_go ? (
        <StatCard icon={CreditCard} label="Billing Estimate">
          <div className="flex items-baseline justify-between">
            <div>
              <div className="text-2xl font-mono font-semibold text-[var(--color-text-primary)]">
                ${(stats.estimated_cost ?? 0).toFixed(2)}
              </div>
              <div className="text-xs text-[var(--color-text-secondary)] mt-1">Estimated for this billing period</div>
            </div>
            <div className="text-right">
              <div className="text-xs font-mono text-[var(--color-text-secondary)]">{stats.tokens_used.toLocaleString()} tokens used</div>
              <div className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">${(stats.cost_per_million_tokens ?? 0).toFixed(2)} / 1M tokens</div>
            </div>
          </div>
        </StatCard>
      ) : (
        <div className="p-4 border border-dashed border-[var(--color-border-main)] rounded-[var(--radius-global)] flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-[var(--color-text-primary)] flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-[var(--color-accent)]" /> Need higher limits?
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] mt-1">
              {stats.plan_id === 'free_trial' && "Upgrade to Basic or Premium for higher monthly limits."}
              {stats.plan_id === 'basic' && "Upgrade to Premium for full feature access and higher limits."}
              {stats.plan_id === 'premium' && "Switch to Executive for unmetered, pay-as-you-go usage."}
            </p>
          </div>
        </div>
      )}

      {stats.trial_ends_at && stats.plan_id === 'free_trial' && (
        <p className="text-xs text-[var(--color-text-secondary)]">Trial ends {new Date(stats.trial_ends_at).toLocaleDateString()}</p>
      )}
    </div>
  );
}
