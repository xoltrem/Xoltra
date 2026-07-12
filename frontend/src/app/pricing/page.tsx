'use client';
import { useEffect, useState } from 'react';
import { Check, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { getPlans, upgradePlan, fetchApi } from '@/lib/api';

const PLAN_ORDER = ['free_trial', 'basic', 'premium', 'executive'];
const HIGHLIGHT = 'premium';

export default function PricingPage() {
  const [plans, setPlans] = useState<any[]>([]);
  const [currentPlan, setCurrentPlan] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPlans().then(r => {
      const sorted = [...(r.plans || [])].sort((a, b) => PLAN_ORDER.indexOf(a.id) - PLAN_ORDER.indexOf(b.id));
      setPlans(sorted);
    }).catch(e => setError(e.message));
    fetchApi('/usage/summary').then(s => setCurrentPlan(s.plan_id)).catch(() => {});
  }, []);

  const choose = async (planId: string) => {
    setBusy(planId);
    setError(null);
    try {
      await upgradePlan(planId);
      setCurrentPlan(planId);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold mb-1 tracking-tight">Plans & Pricing</h1>
        <p className="text-[var(--color-text-secondary)] text-sm">Pick the plan that fits how much you run through Xoltra.</p>
      </div>

      {error && <div className="text-xs text-[var(--color-error)]">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {plans.map(p => {
          const isCurrent = currentPlan === p.id;
          const isHighlight = p.id === HIGHLIGHT;
          return (
            <div
              key={p.id}
              className={cn(
                "flex flex-col p-4 rounded-[var(--radius-global)] border",
                isHighlight ? "border-[var(--color-accent)] bg-[var(--color-accent)]/5" : "border-[var(--color-border-main)]"
              )}
            >
              {isHighlight && (
                <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-[var(--color-accent)] mb-2">
                  <Sparkles className="w-3 h-3" /> Most popular
                </div>
              )}
              <div className="text-sm font-semibold mb-1">{p.label}</div>
              <div className="text-xs text-[var(--color-text-secondary)] mb-4">
                {p.pay_as_you_go
                  ? `$${p.cost_per_million}/1M tokens`
                  : p.monthly_tokens
                    ? `${p.monthly_tokens.toLocaleString()} tokens/mo`
                    : 'Unmetered'}
              </div>
              <ul className="space-y-1.5 mb-4 flex-1">
                {p.features.map((f: string) => (
                  <li key={f} className="flex items-center gap-1.5 text-xs text-[var(--color-text-primary)]">
                    <Check className="w-3 h-3 text-[var(--color-success)] shrink-0" />
                    {f.replace(/_/g, ' ')}
                  </li>
                ))}
              </ul>
              <Button
                size="sm"
                variant={isCurrent ? 'outline' : isHighlight ? 'default' : 'outline'}
                disabled={isCurrent || busy === p.id}
                onClick={() => choose(p.id)}
              >
                {isCurrent ? 'Current plan' : busy === p.id ? 'Switching...' : `Choose ${p.label}`}
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
