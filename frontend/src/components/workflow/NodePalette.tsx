'use client';
/**
 * NodePalette — left rail of the editor, populated from the node library.
 * Click a node to append it to the canvas; drag onto the canvas to place it.
 * The library itself is fetched once by the editor page and passed down, so
 * the palette and the config panel share one request.
 */
import { useMemo, useState, type DragEvent } from 'react';
import { Search, ChevronDown, ChevronRight, Play, Cpu, FileText, Box, Wrench } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { NodeDefinition, NodeCategory } from '@/lib/workflow-graph';

const CATEGORY_ORDER: NodeCategory[] = ['trigger', 'ai', 'logic', 'integration', 'utility'];
const CATEGORY_META: Record<NodeCategory, { label: string; icon: React.ComponentType<{ className?: string }> }> = {
  trigger: { label: 'Triggers', icon: Play },
  ai: { label: 'AI', icon: Cpu },
  logic: { label: 'Logic', icon: FileText },
  integration: { label: 'Integrations', icon: Box },
  utility: { label: 'Utilities', icon: Wrench },
};

export const PALETTE_DRAG_TYPE = 'application/xoltra-node-type';

interface NodePaletteProps {
  definitions: NodeDefinition[];
  /** True when the library request failed — shows a hint instead of nodes. */
  loadFailed?: boolean;
  onAdd: (def: NodeDefinition) => void;
}

export function NodePalette({ definitions: defs, loadFailed, onAdd }: NodePaletteProps) {
  const [query, setQuery] = useState('');
  const [collapsed, setCollapsed] = useState<Partial<Record<NodeCategory, boolean>>>({});

  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? defs.filter(d =>
          d.label.toLowerCase().includes(q) ||
          d.node_type.toLowerCase().includes(q) ||
          d.description?.toLowerCase().includes(q))
      : defs;
    const byCat = new Map<NodeCategory, NodeDefinition[]>();
    for (const d of filtered) {
      const cat = (CATEGORY_ORDER.includes(d.category) ? d.category : 'utility') as NodeCategory;
      byCat.set(cat, [...(byCat.get(cat) || []), d]);
    }
    return byCat;
  }, [defs, query]);

  const handleDragStart = (e: DragEvent, def: NodeDefinition) => {
    e.dataTransfer.setData(PALETTE_DRAG_TYPE, JSON.stringify(def));
    e.dataTransfer.effectAllowed = 'move';
  };

  return (
    <aside className="w-[240px] shrink-0 flex flex-col border-r border-[var(--color-border-main)] bg-[var(--color-panel-100)]/60">
      <div className="p-2 border-b border-[var(--color-border-main)]">
        <div className="relative">
          <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-text-secondary)]" />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search nodes..."
            aria-label="Search nodes"
            className="w-full bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] pl-7 pr-2 py-1.5 text-xs focus:outline-none focus:border-[var(--color-accent)]/40"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto no-scrollbar py-1">
        {loadFailed && (
          <div className="px-3 py-2 text-[11px] text-[var(--color-text-secondary)]">
            Node library unavailable — is the backend running?
          </div>
        )}
        {CATEGORY_ORDER.map(cat => {
          const items = grouped.get(cat);
          if (!items?.length) return null;
          const meta = CATEGORY_META[cat];
          const isCollapsed = collapsed[cat] && !query;
          return (
            <div key={cat} className="mb-1">
              <button
                onClick={() => setCollapsed(prev => ({ ...prev, [cat]: !prev[cat] }))}
                className="w-full flex items-center gap-1.5 px-3 py-1.5 text-[10px] uppercase tracking-wider font-medium text-[var(--color-text-secondary)] hover:text-white transition-colors"
              >
                {isCollapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                <meta.icon className="w-3 h-3" />
                {meta.label}
                <span className="ml-auto font-mono">{items.length}</span>
              </button>
              {!isCollapsed && items.map(def => (
                <button
                  key={def.node_type}
                  draggable
                  onDragStart={e => handleDragStart(e, def)}
                  onClick={() => onAdd(def)}
                  title={`${def.description}\n\nClick to add, or drag onto the canvas.`}
                  className={cn(
                    'w-full text-left px-3 py-2 mx-0 flex flex-col gap-0.5 cursor-grab',
                    'hover:bg-[var(--color-panel-200)] transition-colors border-l-2 border-transparent',
                    'hover:border-[var(--color-accent)]/50',
                  )}
                >
                  <span className="text-xs text-[var(--color-text-primary)]">{def.label}</span>
                  <span className="text-[10px] font-mono text-[var(--color-text-secondary)] truncate">{def.node_type}</span>
                </button>
              ))}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
