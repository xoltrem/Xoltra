'use client';
import { useEffect, useState } from 'react';
import { Users, Copy, Check, Loader2, Download, Shield } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { getMyOrgs, getOrgMembers, createOrgInvite, setMemberRole, getOrgAuditLog, exportOrgAuditLogCsv } from '@/lib/api';
import { notify } from '@/lib/notifications';

interface Member {
  user_id: string;
  email: string;
  role: 'owner' | 'admin' | 'member';
  joined_at: string;
}

export function TeamPanel() {
  const [orgId, setOrgId] = useState<string | null>(null);
  const [myRole, setMyRole] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [inviteRole, setInviteRole] = useState<'admin' | 'member'>('member');
  const [inviteCode, setInviteCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const r = await getMyOrgs();
      const org = r.organizations?.[0];
      if (!org) return;
      setOrgId(org.id);
      setMyRole(org.role);
      const m = await getOrgMembers(org.id);
      setMembers(m.members || []);
    } catch (e: any) {
      setError(e.message || 'Failed to load team');
    }
  };

  useEffect(() => { load(); }, []);

  const isAdmin = myRole === 'owner' || myRole === 'admin';

  const invite = async () => {
    if (!orgId) return;
    setBusy(true);
    try {
      const r = await createOrgInvite(orgId, inviteRole);
      setInviteCode(r.code);
    } catch (e: any) {
      setError(e.message || 'Failed to create invite');
    } finally {
      setBusy(false);
    }
  };

  const copyLink = async () => {
    if (!inviteCode || typeof window === 'undefined') return;
    await navigator.clipboard.writeText(`${window.location.origin}/join?code=${inviteCode}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const changeRole = async (userId: string, role: string) => {
    if (!orgId) return;
    try {
      await setMemberRole(orgId, userId, role);
      notify('Role updated', `Member is now ${role}.`);
      load();
    } catch (e: any) {
      notify('Could not update role', e.message);
    }
  };

  const exportAudit = async (format: 'json' | 'csv') => {
    if (!orgId) return;
    try {
      if (format === 'csv') {
        const res = await exportOrgAuditLogCsv(orgId);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `xoltra-audit-${orgId.slice(0, 8)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        const r = await getOrgAuditLog(orgId);
        const blob = new Blob([JSON.stringify(r.entries, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `xoltra-audit-${orgId.slice(0, 8)}.json`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e: any) {
      notify('Export failed', e.message);
    }
  };

  if (error) return <div className="text-xs text-[var(--color-error)]">{error}</div>;
  if (!orgId) return <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading team...</div>;

  return (
    <div className="space-y-5 max-w-lg">
      <div>
        <h2 className="text-sm font-medium flex items-center gap-1.5 mb-1">
          <Users className="w-4 h-4 text-[var(--color-accent)]" /> Team
        </h2>
        <p className="text-xs text-[var(--color-text-secondary)]">
          You're {myRole} on this organization.
        </p>
      </div>

      <div className="space-y-1.5">
        {members.map(m => (
          <div key={m.user_id} className="flex items-center gap-2 text-xs py-1.5 border-b border-[var(--color-border-main)]/50 last:border-0">
            <span className="flex-1 truncate">{m.email}</span>
            {myRole === 'owner' && m.role !== 'owner' ? (
              <select
                value={m.role}
                onChange={e => changeRole(m.user_id, e.target.value)}
                className="bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-2 py-1 text-[10px]"
              >
                <option value="admin">admin</option>
                <option value="member">member</option>
              </select>
            ) : (
              <span className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-[#151515] border border-[var(--color-border-main)] text-[var(--color-text-secondary)]">
                {m.role}
              </span>
            )}
          </div>
        ))}
      </div>

      {isAdmin && (
        <div className="border-t border-[var(--color-border-main)] pt-4 space-y-2">
          <div className="flex items-center gap-2">
            <select
              value={inviteRole}
              onChange={e => setInviteRole(e.target.value as 'admin' | 'member')}
              className="bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-2 py-1.5 text-xs"
            >
              <option value="member">Invite as member</option>
              <option value="admin">Invite as admin</option>
            </select>
            <Button size="sm" variant="outline" onClick={invite} disabled={busy}>
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Generate invite'}
            </Button>
          </div>
          {inviteCode && (
            <div className="flex items-center gap-2">
              <input
                readOnly
                value={`${typeof window !== 'undefined' ? window.location.origin : ''}/join?code=${inviteCode}`}
                onClick={e => (e.target as HTMLInputElement).select()}
                className="flex-1 bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs font-mono text-[var(--color-text-secondary)]"
              />
              <button onClick={copyLink} className="shrink-0 flex items-center gap-1.5 text-xs px-3 py-2 rounded-[var(--radius-global)] bg-[var(--color-panel-200)] border border-[var(--color-border-main)]">
                {copied ? <Check className="w-3.5 h-3.5 text-[var(--color-accent)]" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          )}
        </div>
      )}

      {isAdmin && (
        <div className="border-t border-[var(--color-border-main)] pt-4">
          <h3 className="text-xs font-medium flex items-center gap-1.5 mb-2">
            <Shield className="w-3.5 h-3.5" /> Audit log export
          </h3>
          <p className="text-[11px] text-[var(--color-text-secondary)] mb-2">
            Every AI-node action taken by anyone on this team, allowed or blocked, with the reason.
          </p>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" className="gap-1.5" onClick={() => exportAudit('csv')}>
              <Download className="w-3 h-3" /> Export CSV
            </Button>
            <Button size="sm" variant="outline" className="gap-1.5" onClick={() => exportAudit('json')}>
              <Download className="w-3 h-3" /> Export JSON
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
