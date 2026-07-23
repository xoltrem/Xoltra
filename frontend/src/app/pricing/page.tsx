'use client';
import { useEffect, useState } from 'react';
import { Check, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { getPlans, upgradePlan, fetchApi } from '@/lib/api';

const PLAN_ORDER = ['free_trial', 'basic', 'premium', 'max'];
const HIGHLIGHT = 'premium';

const CARD_COPY: Record<string, { subhead: string; bullets: string[]; button: string }> = {
  free_trial: {
    subhead: '14 days to try everything before you decide.',
    bullets: ['5,000 Weekly Reset Tokens', 'All Agents Unlocked for the Trial', '1-Million Context Window Ready', 'Standard Execution Speed'],
    button: 'Start Free Trial',
  },
  basic: {
    subhead: 'For light syntax evaluation and basic agent testing.',
    bullets: ['56,000 Weekly Reset Tokens', 'Access to 4 Core Agents', '1-Million Context Window Ready', 'Standard Execution Speed'],
    button: 'Start Testing',
  },
  premium: {
    subhead: 'Built for professionals running automated workflows.',
    bullets: ['448,000 Weekly Reset Tokens (8x More)', 'Unlock All 13 Specialized Agents', '1-Million Context Window Ready', 'High-Priority Execution Speed'],
    button: 'Upgrade & Unlock Workforce',
  },
  max: {
    subhead: 'For power users managing massive data operations.',
    bullets: ['1,190,000 Weekly Reset Tokens (21x More)', 'Unlock All 13 Specialized Agents', '1-Million Context Window Ready', 'Exclusive Access to Beta Agent Updates'],
    button: 'Go Max',
  },
};

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

      <div className="rounded-[var(--radius-global)] border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/5 p-3 text-xs text-[var(--color-text-secondary)]">
        Card payment isn't connected yet — choosing a plan below activates it immediately for testing, unverified, rate-limited to 3 changes/hour. This will require real payment once Stripe Checkout is wired up.
      </div>

      {error && <div className="text-xs text-[var(--color-error)]">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {plans.map(p => {
          const isCurrent = currentPlan === p.id;
          const isHighlight = p.id === HIGHLIGHT;
          const copy = CARD_COPY[p.id] || { subhead: '', bullets: p.features?.map((f: string) => f.replace(/_/g, ' ')) || [], button: `Choose ${p.label}` };
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
                  <Sparkles className="w-3 h-3" /> Most Popular
                </div>
              )}
              <div className="text-sm font-semibold">{p.label}</div>
              <div className="text-xl font-mono font-semibold text-[var(--color-text-primary)] mt-1">
                {p.price_cents > 0 ? `$${(p.price_cents / 100).toFixed(0)}` : 'Free'}
                {p.price_cents > 0 && <span className="text-xs text-[var(--color-text-secondary)] font-normal"> / month</span>}
              </div>
              <p className="text-xs text-[var(--color-text-secondary)] mt-1 mb-4">{copy.subhead}</p>
              <ul className="space-y-1.5 mb-4 flex-1">
                {copy.bullets.map((b: string) => (
                  <li key={b} className="flex items-center gap-1.5 text-xs text-[var(--color-text-primary)]">
                    <Check className="w-3 h-3 text-[var(--color-success)] shrink-0" />
                    {b}
                  </li>
                ))}
              </ul>
              {p.overage_allowed && (
                <p className="text-[10px] text-[var(--color-text-secondary)] mb-2">
                  Runs out mid-week? Extra tokens bill at pay-as-you-go rates instead of stopping your work.
                </p>
              )}
              <Button
                size="sm"
                variant={isCurrent ? 'outline' : isHighlight ? 'default' : 'outline'}
                disabled={isCurrent || busy === p.id}
                onClick={() => choose(p.id)}
              >
                {isCurrent ? 'Current plan' : busy === p.id ? 'Switching...' : copy.button}
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
