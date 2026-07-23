'use client';
import { useEffect, useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { onAccountTimeout, clearToken, AccountTimeoutError } from '@/lib/api';

export function SuspendedAccountModal() {
  const [info, setInfo] = useState<AccountTimeoutError | null>(null);

  useEffect(() => {
    return onAccountTimeout((err) => setInfo(err));
  }, []);

  if (!info) return null;

  const expires = new Date(info.timeoutUntil);
  const stillActive = expires.getTime() > Date.now();

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-sm bg-[var(--color-panel-100)] border border-[var(--color-error)]/30 rounded-[var(--radius-global)] p-6 text-center">
        <ShieldAlert className="w-8 h-8 text-[var(--color-error)] mx-auto mb-3" />
        <h2 className="text-base font-medium text-[var(--color-text-primary)] mb-1">Account temporarily suspended</h2>
        <p className="text-xs text-[var(--color-text-secondary)] mb-4">{info.message}</p>
        {stillActive && (
          <p className="text-xs text-[var(--color-text-secondary)] mb-4">
            Access resumes {expires.toLocaleString()}.
          </p>
        )}
        <button
          onClick={() => { clearToken(); window.location.href = '/login'; }}
          className="text-xs px-3 py-2 rounded-[var(--radius-global)] border border-[var(--color-border-main)] text-[var(--color-text-secondary)] hover:text-white transition-colors"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
