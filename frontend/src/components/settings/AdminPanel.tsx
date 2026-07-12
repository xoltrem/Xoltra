'use client';
import { useState } from 'react';
import { CircleDot, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { getAdminHealth, restoreBackup } from '@/lib/api';

export function AdminPanel() {
  const [adminKey, setAdminKey] = useState('');
  const [health, setHealth] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await getAdminHealth(adminKey);
      setHealth(r);
    } catch (e: any) {
      setError(e.message);
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  const doRestore = async () => {
    if (!confirm('This overwrites the live database with the latest backup. Continue?')) return;
    try {
      await restoreBackup(adminKey);
      alert('Restore complete.');
      load();
    } catch (e: any) {
      alert(`Restore failed: ${e.message}`);
    }
  };

  const Dot = ({ ok }: { ok: boolean }) => (
    <CircleDot className={cn("w-3 h-3", ok ? "text-[var(--color-success)]" : "text-[var(--color-error)]")} />
  );

  return (
    <div>
      <h2 className="text-xl font-semibold tracking-tight mb-1">Admin</h2>
      <p className="text-sm text-[var(--color-text-secondary)] mb-4">Backup + system health. Requires the operator admin key.</p>

      <div className="flex gap-2 mb-4">
        <input
          value={adminKey}
          onChange={e => setAdminKey(e.target.value)}
          placeholder="X-Admin-Key"
          type="password"
          className="flex-1 bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs"
        />
        <Button size="sm" onClick={load} disabled={!adminKey || loading} className="gap-1.5">
          <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} /> Check
        </Button>
      </div>

      {error && <div className="text-xs text-[var(--color-error)] mb-3">{error}</div>}

      {health && (
        <div className="space-y-3">
          <div className="p-3 border border-[var(--color-border-main)] rounded-[var(--radius-global)] flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <Dot ok={!!health.backup?.enabled && !health.backup?.error} />
              Backups — {health.backup?.enabled ? (health.backup?.last_snapshot_at ? `last snapshot ${new Date(health.backup.last_snapshot_at).toLocaleString()}` : 'no snapshot yet') : 'disabled'}
            </div>
            <Button size="sm" variant="outline" onClick={doRestore}>Restore latest</Button>
          </div>
          <div className="p-3 border border-[var(--color-border-main)] rounded-[var(--radius-global)] flex items-center gap-2 text-xs">
            <Dot ok={!!health.unity?.connected} />
            Unity — {health.unity?.connected ? `${health.unity.clients} client(s) connected` : 'disconnected'}
          </div>
        </div>
      )}
    </div>
  );
}
