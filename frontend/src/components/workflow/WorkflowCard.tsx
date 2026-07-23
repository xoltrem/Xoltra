'use client';
/**
 * WorkflowCard — dashboard summary card, the entry point into the editor.
 *
 * Interactions (per spec):
 *  - click / double-click anywhere  -> open editor
 *  - Enter / Space when focused    -> open editor
 *  - right-click                    -> context menu (open, run, duplicate, delete)
 */
import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react';
import {
  Workflow as WorkflowIcon, Play, Copy, Trash2, ExternalLink,
  Clock, GitBranch, Zap, Loader2,
} from 'lucide-react';
import { cn, formatDate } from '@/lib/utils';
import type { RunSummary, WorkflowSummary } from '@/lib/workflow-graph';
import { describeGraph, triggerLabel } from '@/lib/workflow-graph';

interface WorkflowCardProps {
  workflow: WorkflowSummary;
  lastRun?: RunSummary | null;
  onOpen: (id: string) => void;
  onRun: (id: string) => Promise<void> | void;
  onDuplicate: (id: string) => Promise<void> | void;
  onDelete: (id: string) => Promise<void> | void;
}

const RUN_STATUS_COLOR: Record<string, string> = {
  success: 'text-[var(--color-success)]',
  failed: 'text-[var(--color-error)]',
  running: 'text-[var(--color-warning)]',
};

export function WorkflowCard({ workflow, lastRun, onOpen, onRun, onDuplicate, onDelete }: WorkflowCardProps) {
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const [busy, setBusy] = useState<'run' | 'duplicate' | 'delete' | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close the context menu on outside click / Escape.
  useEffect(() => {
    if (!menu) return;
    const close = (e: Event) => {
      if (menuRef.current?.contains(e.target as Node)) return;
      setMenu(null);
    };
    const onEsc = (e: globalThis.KeyboardEvent) => { if (e.key === 'Escape') setMenu(null); };
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', onEsc);
    window.addEventListener('blur', () => setMenu(null));
    return () => {
      window.removeEventListener('mousedown', close);
      window.removeEventListener('keydown', onEsc);
    };
  }, [menu]);

  const handleContextMenu = (e: MouseEvent) => {
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY });
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onOpen(workflow.id);
    } else if (e.key === 'Delete') {
      e.preventDefault();
      act('delete', () => onDelete(workflow.id));
    }
  };

  const act = async (kind: 'run' | 'duplicate' | 'delete', fn: () => Promise<void> | void) => {
    setMenu(null);
    setBusy(kind);
    try { await fn(); } finally { setBusy(null); }
  };

  const nodeCount = workflow.graph?.nodes?.length ?? 0;
  const trigger = triggerLabel(workflow.graph);
  const isPublished = workflow.status === 'published';

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        aria-label={`Open workflow ${workflow.name}`}
        onClick={() => onOpen(workflow.id)}
        onDoubleClick={() => onOpen(workflow.id)}
        onKeyDown={handleKeyDown}
        onContextMenu={handleContextMenu}
        className={cn(
          'group text-left w-full flex flex-col gap-3 p-4 cursor-pointer select-none',
          'bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)]',
          'transition-all duration-150 hover:border-[var(--color-border-hover)] hover:bg-[var(--color-panel-200)]/60',
          'hover:shadow-[0_4px_24px_rgba(0,0,0,0.4)] hover:-translate-y-px',
          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--color-accent)]/60',
        )}
      >
        {/* Title row */}
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-[var(--radius-global)] bg-[#151515] border border-[var(--color-border-main)] flex items-center justify-center shrink-0 group-hover:border-[var(--color-accent)]/30 transition-colors">
            <WorkflowIcon className="w-4 h-4 text-[var(--color-text-secondary)] group-hover:text-[var(--color-accent)] transition-colors" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-medium text-[var(--color-text-primary)] truncate">
                {workflow.name}
              </h3>
              <span
                className={cn(
                  'shrink-0 text-[9px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded-full border',
                  isPublished
                    ? 'text-[var(--color-success)] border-[var(--color-success)]/30 bg-[var(--color-success)]/10'
                    : 'text-[var(--color-text-secondary)] border-[var(--color-border-main)] bg-[var(--color-panel-200)]',
                )}
              >
                {workflow.status}
              </span>
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] truncate mt-0.5">
              {describeGraph(workflow.graph)}
            </p>
          </div>
          <ExternalLink className="w-3.5 h-3.5 text-[var(--color-text-secondary)] opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-1" />
        </div>

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[var(--color-text-secondary)]">
          {trigger && (
            <span className="flex items-center gap-1.5" title="Trigger">
              <Zap className="w-3 h-3 text-[var(--color-accent)]/70" /> {trigger}
            </span>
          )}
          <span className="flex items-center gap-1.5" title="Node count">
            <GitBranch className="w-3 h-3" /> {nodeCount} node{nodeCount === 1 ? '' : 's'}
          </span>
          <span className="flex items-center gap-1.5" title="Last modified">
            <Clock className="w-3 h-3" /> {formatDate(workflow.updated_at)}
          </span>
          {lastRun && (
            <span className="flex items-center gap-1.5" title="Last execution">
              <Play className="w-3 h-3" />
              <span className={RUN_STATUS_COLOR[lastRun.status] || ''}>{lastRun.status}</span>
              <span>{formatDate(lastRun.started_at)}</span>
            </span>
          )}
          {busy && <Loader2 className="w-3 h-3 animate-spin text-[var(--color-accent)]" />}
        </div>
      </div>

      {/* Context menu */}
      {menu && (
        <div
          ref={menuRef}
          role="menu"
          style={{ left: menu.x, top: menu.y }}
          className="fixed z-50 min-w-[160px] py-1 bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] shadow-2xl text-xs"
        >
          <MenuItem icon={ExternalLink} onClick={() => { setMenu(null); onOpen(workflow.id); }}>
            Open
          </MenuItem>
          <MenuItem icon={Play} onClick={() => act('run', () => onRun(workflow.id))}>
            Run now
          </MenuItem>
          <MenuItem icon={Copy} onClick={() => act('duplicate', () => onDuplicate(workflow.id))}>
            Duplicate
          </MenuItem>
          <div className="my-1 border-t border-[var(--color-border-main)]" />
          <MenuItem icon={Trash2} destructive onClick={() => act('delete', () => onDelete(workflow.id))}>
            Delete
          </MenuItem>
        </div>
      )}
    </>
  );
}

function MenuItem({ icon: Icon, destructive, onClick, children }: {
  icon: React.ComponentType<{ className?: string }>;
  destructive?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      role="menuitem"
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      className={cn(
        'w-full flex items-center gap-2 px-3 py-1.5 text-left transition-colors',
        destructive
          ? 'text-[var(--color-error)] hover:bg-[var(--color-error)]/10'
          : 'text-[var(--color-text-primary)] hover:bg-[var(--color-panel-200)]',
      )}
    >
      <Icon className="w-3.5 h-3.5" /> {children}
    </button>
  );
}
