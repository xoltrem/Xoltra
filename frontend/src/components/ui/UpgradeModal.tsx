'use client';
import { useEffect, useState } from 'react';
import { Sparkles, X } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { fetchApi } from '@/lib/api';

const DISMISS_KEY = 'xoltra_upgrade_popup_dismissed_at';
const DISMISS_COOLDOWN_MS = 24 * 60 * 60 * 1000; // don't nag more than once/day

export function UpgradeModal() {
  const [reason, setReason] = useState<string | null>(null);

  useEffect(() => {
    const lastDismissed = Number(localStorage.getItem(DISMISS_KEY) || 0);
    if (Date.now() - lastDismissed < DISMISS_COOLDOWN_MS) return;

    fetchApi('/usage/summary').then(summary => {
      if (summary.plan_id !== 'free_trial') return;

      if (summary.usage_warning?.level === 'critical') {
        setReason(`You've used ${summary.usage_warning.pct}% of your trial's token limit.`);
        return;
      }
      if (summary.trial_ends_at) {
        const daysLeft = (new Date(summary.trial_ends_at).getTime() - Date.now()) / 86_400_000;
        if (daysLeft <= 3 && daysLeft >= 0) {
          setReason(`Your free trial ends in ${Math.max(1, Math.round(daysLeft))} day${daysLeft >= 1.5 ? 's' : ''}.`);
        }
      }
    }).catch(() => {});
  }, []);

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
    setReason(null);
  };

  if (!reason) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-sm bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] shadow-2xl p-5">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2 text-[var(--color-accent)]">
            <Sparkles className="w-5 h-5" />
            <span className="text-sm font-semibold">Get more out of Xoltra</span>
          </div>
          <button onClick={dismiss} className="text-[var(--color-text-secondary)] hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
        <p className="text-sm text-[var(--color-text-primary)] mb-1">{reason}</p>
        <p className="text-xs text-[var(--color-text-secondary)] mb-4">
          Upgrade to Basic, Premium, or Executive for more tokens, workflows, and features like OneDrive cloud backup.
        </p>
        <div className="flex gap-2">
          <Button size="sm" className="flex-1" onClick={() => { dismiss(); window.location.href = '/pricing'; }}>
            View plans
          </Button>
          <Button size="sm" variant="outline" onClick={dismiss}>Remind me later</Button>
        </div>
      </div>
    </div>
  );
}
