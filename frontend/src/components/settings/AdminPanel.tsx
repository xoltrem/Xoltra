'use client';
import { useState } from 'react';
import { CircleDot, RefreshCw, ShieldAlert, Trash2, ScrollText } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { getAdminHealth, restoreBackup, getActiveTimeouts, timeoutUser, clearUserTimeout, getAuditLog } from '@/lib/api';

export function AdminPanel() {
  const [adminKey, setAdminKey] = useState('');
  const [health, setHealth] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [timeouts, setTimeouts] = useState<any[] | null>(null);
  const [modError, setModError] = useState<string | null>(null);
  const [newUserId, setNewUserId] = useState('');
  const [newReason, setNewReason] = useState('');
  const [newDuration, setNewDuration] = useState('60');
  const [modBusy, setModBusy] = useState(false);

  const [auditEntries, setAuditEntries] = useState<any[] | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditUserFilter, setAuditUserFilter] = useState('');

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
    loadTimeouts();
    loadAuditLog();
  };

  const loadTimeouts = async () => {
    try {
      const r = await getActiveTimeouts(adminKey);
      setTimeouts(r.timeouts);
      setModError(null);
    } catch (e: any) {
      setModError(e.message);
    }
  };

  const loadAuditLog = async () => {
    try {
      const r = await getAuditLog(adminKey, 50, auditUserFilter || undefined);
      setAuditEntries(r.entries);
      setAuditError(null);
    } catch (e: any) {
      setAuditError(e.message);
    }
  };

  const handleTimeoutUser = async () => {
    if (!newUserId || !newReason || !newDuration) return;
    setModBusy(true);
    try {
      await timeoutUser(adminKey, newUserId, newReason, parseInt(newDuration, 10));
      setNewUserId(''); setNewReason(''); setNewDuration('60');
      await loadTimeouts();
    } catch (e: any) {
      setModError(e.message);
    } finally {
      setModBusy(false);
    }
  };

  const handleClearTimeout = async (userId: string) => {
    setModBusy(true);
    try {
      await clearUserTimeout(adminKey, userId);
      await loadTimeouts();
    } catch (e: any) {
      setModError(e.message);
    } finally {
      setModBusy(false);
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

      {adminKey && (
        <div className="mt-6 pt-4 border-t border-[var(--color-border-main)]">
          <h3 className="text-sm font-medium flex items-center gap-1.5 mb-3">
            <ShieldAlert className="w-3.5 h-3.5" /> ToS Timeouts
          </h3>

          <div className="flex gap-2 mb-3">
            <input
              value={newUserId}
              onChange={e => setNewUserId(e.target.value)}
              placeholder="user_id"
              className="flex-1 bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs"
            />
            <input
              value={newReason}
              onChange={e => setNewReason(e.target.value)}
              placeholder="reason"
              className="flex-1 bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs"
            />
            <input
              value={newDuration}
              onChange={e => setNewDuration(e.target.value)}
              placeholder="minutes"
              type="number"
              min="1"
              className="w-24 bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs"
            />
            <Button size="sm" variant="outline" onClick={handleTimeoutUser} disabled={modBusy || !newUserId || !newReason}>
              Timeout
            </Button>
          </div>

          {modError && <div className="text-xs text-[var(--color-error)] mb-3">{modError}</div>}

          {timeouts && timeouts.length === 0 && (
            <p className="text-xs text-[var(--color-text-secondary)]">No accounts currently timed out.</p>
          )}

          {timeouts && timeouts.length > 0 && (
            <div className="space-y-2">
              {timeouts.map(t => (
                <div key={t.id} className="p-3 border border-[var(--color-border-main)] rounded-[var(--radius-global)] flex items-center justify-between text-xs">
                  <div>
                    <div className="text-[var(--color-text-primary)]">{t.user_id}</div>
                    <div className="text-[var(--color-text-secondary)]">
                      {t.reason} — expires {new Date(t.expires_at).toLocaleString()} ({t.category}, by {t.created_by})
                    </div>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => handleClearTimeout(t.user_id)} disabled={modBusy} className="gap-1.5">
                    <Trash2 className="w-3.5 h-3.5" /> Clear
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {adminKey && (
        <div className="mt-6 pt-4 border-t border-[var(--color-border-main)]">
          <h3 className="text-sm font-medium flex items-center gap-1.5 mb-1">
            <ScrollText className="w-3.5 h-3.5" /> Audit Log
          </h3>
          <p className="text-xs text-[var(--color-text-secondary)] mb-3">
            Recent Permission Bridge activity — every AI-node action, allowed or blocked, with the reason.
            Filter by tenant below; entries logged before this filter shipped won't have a user_id to match.
          </p>

          <div className="flex gap-2 mb-3">
            <input
              value={auditUserFilter}
              onChange={e => setAuditUserFilter(e.target.value)}
              placeholder="user_id (optional filter)"
              className="flex-1 bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs"
            />
            <Button size="sm" variant="outline" onClick={loadAuditLog}>Filter</Button>
          </div>

          {auditError && <div className="text-xs text-[var(--color-error)] mb-3">{auditError}</div>}

          {auditEntries && auditEntries.length === 0 && (
            <p className="text-xs text-[var(--color-text-secondary)]">No audit entries yet.</p>
          )}

          {auditEntries && auditEntries.length > 0 && (
            <div className="space-y-1.5 max-h-96 overflow-y-auto">
              {auditEntries.slice().reverse().map((entry, i) => {
                const outcome = entry.outcome as string;
                const outcomeColor =
                  outcome === 'allowed' ? 'text-[var(--color-success)]' :
                  outcome === 'blocked' ? 'text-[var(--color-error)]' :
                  'text-[var(--color-warning,#c9a227)]';
                return (
                  <div key={i} className="p-2.5 border border-[var(--color-border-main)] rounded-[var(--radius-global)] text-xs">
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="font-medium text-[var(--color-text-primary)]">{entry.node_name}</span>
                      <span className={cn("uppercase text-[10px] font-semibold", outcomeColor)}>{outcome}</span>
                    </div>
                    <div className="text-[var(--color-text-secondary)]">{entry.action}</div>
                    <div className="text-[var(--color-text-secondary)] mt-0.5">{entry.reason}</div>
                    <div className="text-[var(--color-text-secondary)] opacity-70 mt-1">
                      {entry.user_id ? `user: ${entry.user_id} · ` : ''}{new Date(entry.timestamp).toLocaleString()}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
