'use client';
/**
 * DiffViewer.tsx — unified-diff renderer + patch approval modal.
 * Shows every file diff in the active patch with Apply / Rollback / Close.
 */
import { X, Check, Undo2, FileDiff } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWorkspaceStore } from '@/stores/workspace';

function DiffBlock({ diff }: { diff: string }) {
  if (!diff.trim()) return <div className="text-xs text-[var(--color-text-secondary)] px-3 py-2">(no content change)</div>;
  return (
    <pre className="text-[12px] leading-5 font-mono overflow-x-auto px-3 py-2">
      {diff.split('\n').map((line, i) => {
        let cls = 'text-[#9a9a9a]';
        if (line.startsWith('+') && !line.startsWith('+++')) cls = 'text-emerald-400 bg-emerald-950/40';
        else if (line.startsWith('-') && !line.startsWith('---')) cls = 'text-red-400 bg-red-950/40';
        else if (line.startsWith('@@')) cls = 'text-sky-400';
        else if (line.startsWith('+++') || line.startsWith('---')) cls = 'text-[var(--color-text-secondary)] font-semibold';
        return <div key={i} className={cn('px-1 whitespace-pre', cls)}>{line || ' '}</div>;
      })}
    </pre>
  );
}

export function DiffViewer() {
  const { activePatch, closePatch, approvePatch, undoPatch } = useWorkspaceStore();
  if (!activePatch) return null;

  const statusColor = {
    proposed: 'text-amber-400 border-amber-400/30 bg-amber-400/10',
    applied: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10',
    failed: 'text-red-400 border-red-400/30 bg-red-400/10',
    rolled_back: 'text-[var(--color-text-secondary)] border-[var(--color-border-main)] bg-transparent',
  }[activePatch.status];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      <div className="w-full max-w-4xl max-h-[85vh] flex flex-col bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] shadow-2xl">
        {/* header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--color-border-main)] shrink-0">
          <FileDiff className="w-4 h-4 text-[var(--color-accent)]" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-white truncate">{activePatch.title}</div>
            <div className="text-xs text-[var(--color-text-secondary)]">
              {activePatch.operations.length} operation{activePatch.operations.length === 1 ? '' : 's'} · patch {activePatch.id}
            </div>
          </div>
          <span className={cn('text-[10px] px-2 py-0.5 rounded border font-mono uppercase', statusColor)}>
            {activePatch.status}
          </span>
          <button onClick={closePatch} className="p-1 text-[var(--color-text-secondary)] hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* operations summary */}
        <div className="px-4 py-2 border-b border-[var(--color-border-main)] flex flex-wrap gap-1.5 shrink-0">
          {activePatch.operations.map((op, i) => (
            <span key={i} className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-[var(--color-panel-200)] text-[var(--color-text-secondary)]">
              {op.type} {op.path}{op.to ? ` → ${op.to}` : ''}
            </span>
          ))}
        </div>

        {/* diffs */}
        <div className="flex-1 overflow-y-auto divide-y divide-[var(--color-border-main)]">
          {(activePatch.diffs ?? []).map((d) => (
            <div key={d.path}>
              <div className="sticky top-0 bg-[var(--color-panel-200)] px-3 py-1.5 text-xs font-mono text-white">
                {d.path}
              </div>
              <DiffBlock diff={d.diff} />
            </div>
          ))}
        </div>

        {/* actions */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[var(--color-border-main)] shrink-0">
          {activePatch.status === 'proposed' && (
            <button
              onClick={() => approvePatch(activePatch.id)}
              className="flex items-center gap-1.5 px-4 py-2 text-sm rounded-[var(--radius-global)] bg-[var(--color-accent)] text-black font-medium hover:opacity-90"
            >
              <Check className="w-4 h-4" /> Apply patch
            </button>
          )}
          {activePatch.status === 'applied' && (
            <button
              onClick={() => undoPatch(activePatch.id)}
              className="flex items-center gap-1.5 px-4 py-2 text-sm rounded-[var(--radius-global)] border border-[var(--color-border-main)] text-white hover:bg-[var(--color-panel-200)]"
            >
              <Undo2 className="w-4 h-4" /> Roll back
            </button>
          )}
          <button
            onClick={closePatch}
            className="px-4 py-2 text-sm rounded-[var(--radius-global)] text-[var(--color-text-secondary)] hover:text-white"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
