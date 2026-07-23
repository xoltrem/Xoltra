'use client';
import { useEffect, useState } from 'react';
import { MonitorSmartphone } from 'lucide-react';
import { getSessions } from '@/lib/api';

interface SessionEvent { ip: string; user_agent: string; event: string; created_at: string; }

export function SecurityPanel() {
  const [sessions, setSessions] = useState<SessionEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSessions().then(r => setSessions(r.sessions)).catch(e => setError(e.message));
  }, []);

  return (
    <div>
      <h2 className="text-xl font-semibold tracking-tight mb-1">Security</h2>
      <p className="text-sm text-[var(--color-text-secondary)] mb-4">Recent sign-ins to your account.</p>
      {error && <div className="text-xs text-[var(--color-error)]">{error}</div>}
      <div className="border border-[var(--color-border-main)] rounded-[var(--radius-global)] divide-y divide-[var(--color-border-main)]">
        {sessions.length === 0 && !error && (
          <div className="p-4 text-xs text-[var(--color-text-secondary)]">No recent activity.</div>
        )}
        {sessions.map((s, i) => (
          <div key={i} className="p-3 flex items-center gap-3 text-xs">
            <MonitorSmartphone className="w-4 h-4 text-[var(--color-text-secondary)] shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-[var(--color-text-primary)] capitalize">{s.event.replace('_', ' ')}</div>
              <div className="text-[var(--color-text-secondary)] truncate">{s.ip} — {s.user_agent}</div>
            </div>
            <div className="text-[var(--color-text-secondary)] shrink-0">{new Date(s.created_at).toLocaleString()}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
