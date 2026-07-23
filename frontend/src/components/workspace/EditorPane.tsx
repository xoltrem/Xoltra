'use client';
/**
 * EditorPane.tsx — multi-file editor with tabs.
 * Textarea-based (zero new deps, matches current bundle). Monaco can be
 * swapped in later behind the same store contract.
 */
import { X, Save, Circle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWorkspaceStore } from '@/stores/workspace';

export function EditorPane() {
  const { openFiles, activePath, setActivePath, closeFile, editFile, saveFile } = useWorkspaceStore();
  const active = openFiles.find((f) => f.path === activePath);

  return (
    <div className="flex flex-col h-full min-w-0">
      {/* tabs */}
      <div className="flex items-center border-b border-[var(--color-border-main)] overflow-x-auto shrink-0">
        {openFiles.map((f) => (
          <div
            key={f.path}
            onClick={() => setActivePath(f.path)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-2 text-xs border-r border-[var(--color-border-main)] cursor-pointer whitespace-nowrap',
              f.path === activePath
                ? 'bg-[var(--color-panel-200)] text-white'
                : 'text-[var(--color-text-secondary)] hover:text-white',
            )}
          >
            {f.dirty && <Circle className="w-2 h-2 fill-[var(--color-accent)] text-[var(--color-accent)]" />}
            <span>{f.path.split('/').pop()}</span>
            <button
              onClick={(e) => { e.stopPropagation(); closeFile(f.path); }}
              className="p-0.5 hover:text-red-400"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        ))}
        {active && (
          <button
            onClick={() => saveFile(active.path)}
            disabled={!active.dirty}
            className={cn(
              'ml-auto mr-2 flex items-center gap-1 px-2 py-1 text-xs rounded',
              active.dirty
                ? 'text-[var(--color-accent)] hover:bg-[var(--color-panel-200)]'
                : 'text-[var(--color-text-secondary)] opacity-50',
            )}
            title="Save (checkpointed)"
          >
            <Save className="w-3.5 h-3.5" /> Save
          </button>
        )}
      </div>

      {/* editor body */}
      {active ? (
        <textarea
          value={active.content}
          onChange={(e) => editFile(active.path, e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
              e.preventDefault();
              saveFile(active.path);
            }
          }}
          spellCheck={false}
          className="flex-1 w-full resize-none bg-[#0d0d0d] text-[13px] leading-5 font-mono text-[#e4e4e4] p-4 outline-none"
        />
      ) : (
        <div className="flex-1 flex items-center justify-center text-sm text-[var(--color-text-secondary)]">
          Open a file from the explorer, or give the agent an instruction.
        </div>
      )}
    </div>
  );
}
