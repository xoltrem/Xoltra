'use client';
import { useEffect, useState } from 'react';
import { Gift, Copy, Check, Loader2 } from 'lucide-react';
import { getReferralStats } from '@/lib/api';

export function ReferralsPanel() {
  const [stats, setStats] = useState<{ code: string; signup_count: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getReferralStats()
      .then(r => setStats({ code: r.code, signup_count: r.signup_count }))
      .catch(e => setError(e.message || 'Failed to load referral info'));
  }, []);

  const link = stats && typeof window !== 'undefined'
    ? `${window.location.origin}/login?ref=${stats.code}`
    : '';

  const copy = async () => {
    if (!link) return;
    await navigator.clipboard.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-4 max-w-md">
      <div>
        <h2 className="text-sm font-medium flex items-center gap-1.5 mb-1">
          <Gift className="w-4 h-4 text-[var(--color-accent)]" /> Invite & Referrals
        </h2>
        <p className="text-xs text-[var(--color-text-secondary)]">
          If someone you send this to is also paying for automation and AI separately, that's exactly who Xoltra was built for.
        </p>
      </div>

      {error && <div className="text-xs text-[var(--color-error)]">{error}</div>}

      {!stats && !error && (
        <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading...
        </div>
      )}

      {stats && (
        <>
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={link}
              onClick={e => (e.target as HTMLInputElement).select()}
              className="flex-1 bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs text-[var(--color-text-secondary)] font-mono"
            />
            <button
              onClick={copy}
              className="shrink-0 flex items-center gap-1.5 text-xs px-3 py-2 rounded-[var(--radius-global)] bg-[var(--color-panel-200)] border border-[var(--color-border-main)] hover:border-[var(--color-accent)]/40 transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-[var(--color-accent)]" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>

          <div className="border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-3">
            <p className="text-2xl font-semibold">{stats.signup_count}</p>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {stats.signup_count === 1 ? 'person has' : 'people have'} signed up with your link
            </p>
          </div>
        </>
      )}
    </div>
  );
}
