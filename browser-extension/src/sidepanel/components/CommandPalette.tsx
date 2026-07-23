/**
 * CommandPalette — Ctrl+K inside the side panel. Mirrors the web app's
 * palette interaction: fuzzy-ish filter, arrow keys, Enter to execute.
 */
import { useEffect, useMemo, useRef, useState } from 'react';

export interface PaletteCommand {
  id: string;
  title: string;
  hint?: string;
  run: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  commands: PaletteCommand[];
  onClose: () => void;
}

export function CommandPalette({ open, commands, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery('');
      setSelected(0);
      // Focus after the element mounts.
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter(c => c.title.toLowerCase().includes(q));
  }, [commands, query]);

  useEffect(() => {
    if (selected >= filtered.length) setSelected(Math.max(0, filtered.length - 1));
  }, [filtered.length, selected]);

  if (!open) return null;

  const execute = (cmd: PaletteCommand | undefined) => {
    if (!cmd) return;
    onClose();
    cmd.run();
  };

  return (
    <div className="palette-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette" role="dialog" aria-label="Command palette">
        <input
          ref={inputRef}
          value={query}
          placeholder="Type a command or workflow name…"
          onChange={e => { setQuery(e.target.value); setSelected(0); }}
          onKeyDown={e => {
            if (e.key === 'Escape') onClose();
            else if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, filtered.length - 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)); }
            else if (e.key === 'Enter') execute(filtered[selected]);
          }}
        />
        <div className="palette-list" role="listbox">
          {filtered.length === 0 && <div className="empty">Nothing matches.</div>}
          {filtered.map((c, i) => (
            <button
              key={c.id}
              role="option"
              aria-selected={i === selected}
              className={`palette-item ${i === selected ? 'selected' : ''}`}
              onMouseEnter={() => setSelected(i)}
              onClick={() => execute(c)}
            >
              <span className="truncate">{c.title}</span>
              {c.hint && <span className="hint">{c.hint}</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
