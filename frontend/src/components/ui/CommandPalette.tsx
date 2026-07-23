'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search, Workflow, Settings, Database, Users, LayoutTemplate, Activity, BookOpen, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores';
const COMMANDS = [
  { id: 'dash', label: 'Go to Dashboard', icon: Activity, href: '/' },
  { id: 'wf', label: 'Workflows', icon: Workflow, href: '/workflows' },
  { id: 'tpl', label: 'Templates', icon: LayoutTemplate, href: '/templates' },
  { id: 'int', label: 'Integrations', icon: Database, href: '/integrations' },
  { id: 'agt', label: 'Agents', icon: Users, href: '/agents' },
  { id: 'know', label: 'Knowledge Base', icon: BookOpen, href: '/knowledge' },
  { id: 'exec', label: 'Executions', icon: Activity, href: '/executions' },
  { id: 'audit', label: 'Audit Logs', icon: ShieldAlert, href: '/audit' },
  { id: 'set', label: 'Settings', icon: Settings, href: '/settings' },
];
export function CommandPalette() {
  const router = useRouter();
  const { searchOpen, setSearchOpen } = useUIStore();
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setSearchOpen(!searchOpen);
      }
    };
    document.addEventListener('keydown', down);
    return () => document.removeEventListener('keydown', down);
  }, [searchOpen, setSearchOpen]);
  const filtered = COMMANDS.filter(c => c.label.toLowerCase().includes(query.toLowerCase()));
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(i => (i + 1) % filtered.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(i => (i - 1 + filtered.length) % filtered.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const item = filtered[selectedIndex];
      if (item) {
        router.push(item.href);
        setSearchOpen(false);
        setQuery('');
      }
    } else if (e.key === 'Escape') {
      setSearchOpen(false);
    }
  };
  if (!searchOpen) return null;
  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-start justify-center pt-[15vh]">
      <div 
        className="fixed inset-0" 
        onClick={() => setSearchOpen(false)}
      />
      <div 
        className="relative w-full max-w-xl bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200"
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-center px-4 border-b border-[var(--color-border-main)]">
          <Search className="w-5 h-5 text-[var(--color-text-secondary)] shrink-0" />
          <input 
            autoFocus
            className="flex-1 bg-transparent border-none py-4 px-3 text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none"
            placeholder="Type a command or search..."
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <kbd className="hidden sm:inline-flex h-5 items-center gap-1 rounded bg-[#202020] px-1.5 font-mono text-[10px] font-medium text-[var(--color-text-secondary)]">
            ESC
          </kbd>
        </div>
        
        <div className="max-h-[300px] overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <div className="py-6 text-center text-sm text-[var(--color-text-secondary)]">
              No results found.
            </div>
          ) : (
            filtered.map((item, index) => (
              <button
                key={item.id}
                onClick={() => {
                  router.push(item.href);
                  setSearchOpen(false);
                  setQuery('');
                }}
                onMouseEnter={() => setSelectedIndex(index)}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors",
                  index === selectedIndex 
                    ? "bg-[var(--color-accent)]/10 text-[var(--color-accent)]" 
                    : "text-[var(--color-text-secondary)] hover:bg-[var(--color-panel-200)] hover:text-[var(--color-text-primary)]"
                )}
              >
                <item.icon className="w-4 h-4" />
                {item.label}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
