'use client';
import { useEffect, useState } from 'react';
import { Cloud, CloudUpload, Lock, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { getOneDriveStatus, connectOneDrive, runOneDriveBackup } from '@/lib/api';

export function OneDrivePanel() {
  const [status, setStatus] = useState<any>(null);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => getOneDriveStatus().then(setStatus).catch(e => setError(e.message));
  useEffect(() => { load(); }, []);

  const connect = async () => {
    try {
      const r = await connectOneDrive();
      window.location.href = r.auth_url;
    } catch (e: any) {
      setError(e.message);
    }
  };

  const backup = async () => {
    setLoading(true);
    setError(null);
    setSummary(null);
    try {
      const r = await runOneDriveBackup();
      setSummary(r.summary);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (!status) return null;

  if (!status.premium) {
    return (
      <div className="p-4 border border-dashed border-[var(--color-border-main)] rounded-[var(--radius-global)] flex items-center gap-3 text-sm">
        <Lock className="w-4 h-4 text-[var(--color-text-secondary)]" />
        <div>
          <div className="font-medium">OneDrive Cloud Backup</div>
          <div className="text-xs text-[var(--color-text-secondary)]">Available on Premium and Executive plans.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Cloud className="w-4 h-4 text-[var(--color-accent)]" /> OneDrive Cloud Backup
      </div>
      <p className="text-xs text-[var(--color-text-secondary)]">
        Save a copy of your goals, workflows, insights, and documents to your own OneDrive.
      </p>

      {!status.configured && (
        <div className="text-xs text-[var(--color-warning)]">OneDrive integration is not configured on this server.</div>
      )}
      {error && <div className="text-xs text-[var(--color-error)]">{error}</div>}

      {!status.connected ? (
        <Button size="sm" onClick={connect} disabled={!status.configured} className="gap-1.5">
          <Cloud className="w-3.5 h-3.5" /> Connect OneDrive
        </Button>
      ) : (
        <Button size="sm" onClick={backup} disabled={loading} className="gap-1.5">
          <CloudUpload className="w-3.5 h-3.5" /> {loading ? 'Backing up...' : 'Back up now'}
        </Button>
      )}

      {summary && (
        <div className="p-3 border border-[var(--color-success)]/30 bg-[var(--color-success)]/10 rounded-[var(--radius-global)] text-xs space-y-1">
          <div className="flex items-center gap-1.5 text-[var(--color-success)] font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" /> Backup complete
          </div>
          <div>{summary.filename} — {(summary.size_bytes / 1024).toFixed(1)} KB</div>
          <div className="text-[var(--color-text-secondary)]">
            {summary.goals_saved} goals · {summary.workflows_saved} workflows · {summary.insights_saved} insights · {summary.documents_saved} documents
          </div>
          <div className="text-[var(--color-text-secondary)]">Saved {new Date(summary.saved_at).toLocaleString()}</div>
        </div>
      )}
    </div>
  );
}
