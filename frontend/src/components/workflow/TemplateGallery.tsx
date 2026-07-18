'use client';
import { useEffect, useState } from 'react';
import { LayoutTemplate, Plus, Trash2, Globe, Lock, Search, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import {
  getTemplates, instantiateTemplate, deleteTemplate, saveAsTemplate,
  setTemplatePublished, getPublicTemplates, useTemplate,
} from '@/lib/api';
import { notify } from '@/lib/notifications';

const CATEGORIES = ['sales', 'support', 'marketing', 'ops', 'engineering', 'personal', 'other'] as const;

interface TemplateGalleryProps {
  workflowId?: string;
  onInstantiated?: () => void;
}

export function TemplateGallery({ workflowId, onInstantiated }: TemplateGalleryProps) {
  const [tab, setTab] = useState<'mine' | 'marketplace'>('mine');
  const [templates, setTemplates] = useState<any[]>([]);
  const [publicTemplates, setPublicTemplates] = useState<any[]>([]);
  const [category, setCategory] = useState('');
  const [query, setQuery] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadMine = () => getTemplates().then(r => setTemplates(r.templates || [])).catch(() => {});
  const loadPublic = () =>
    getPublicTemplates(category || undefined, query || undefined)
      .then(r => setPublicTemplates(r.templates || []))
      .catch(() => {});

  useEffect(() => { loadMine(); }, []);
  useEffect(() => { if (tab === 'marketplace') loadPublic(); }, [tab, category]);

  // debounce search
  useEffect(() => {
    if (tab !== 'marketplace') return;
    const t = setTimeout(loadPublic, 300);
    return () => clearTimeout(t);
  }, [query]);

  const saveCurrent = async () => {
    if (!workflowId) return;
    const name = prompt('Template name?');
    if (!name) return;
    await saveAsTemplate(workflowId, name);
    loadMine();
  };

  const use = async (id: string, fromMarketplace: boolean) => {
    setBusyId(id);
    try {
      if (fromMarketplace) {
        await useTemplate(id);
        notify('Template added', 'Rebuilt as a new draft workflow in your account.');
      } else {
        await instantiateTemplate(id);
      }
      onInstantiated?.();
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (id: string) => {
    await deleteTemplate(id);
    loadMine();
  };

  const togglePublish = async (t: any) => {
    setBusyId(t.id);
    try {
      await setTemplatePublished(t.id, !t.is_public);
      notify(
        !t.is_public ? 'Published to marketplace' : 'Made private',
        !t.is_public ? `${t.name} is now visible to everyone.` : `${t.name} is no longer public.`
      );
      loadMine();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1">
          <TabButton active={tab === 'mine'} onClick={() => setTab('mine')} icon={<LayoutTemplate className="w-3.5 h-3.5" />}>
            My Templates
          </TabButton>
          <TabButton active={tab === 'marketplace'} onClick={() => setTab('marketplace')} icon={<Sparkles className="w-3.5 h-3.5" />}>
            Marketplace
          </TabButton>
        </div>
        {tab === 'mine' && workflowId && (
          <Button size="sm" variant="outline" className="gap-1" onClick={saveCurrent}>
            <Plus className="w-3 h-3" /> Save as template
          </Button>
        )}
      </div>

      {tab === 'marketplace' && (
        <div className="flex items-center gap-2 mb-2">
          <div className="relative flex-1">
            <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-text-secondary)]" />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search public templates..."
              className="w-full bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] pl-7 pr-2 py-1.5 text-xs focus:outline-none focus:border-[var(--color-accent)]/40"
            />
          </div>
          <select
            value={category}
            onChange={e => setCategory(e.target.value)}
            className="bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-2 py-1.5 text-xs focus:outline-none"
          >
            <option value="">All categories</option>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      )}

      {tab === 'mine' && (
        <>
          {templates.length === 0 && (
            <div className="text-xs text-[var(--color-text-secondary)]">No templates saved yet.</div>
          )}
          <div className="space-y-1">
            {templates.map(t => (
              <div key={t.id} className="flex items-center gap-2 text-xs py-1.5 border-b border-[var(--color-border-main)]/50 last:border-0">
                <button
                  onClick={() => togglePublish(t)}
                  disabled={busyId === t.id}
                  title={t.is_public ? 'Public — click to make private' : 'Private — click to publish'}
                  className={cn(
                    "shrink-0 transition-colors",
                    t.is_public ? "text-[var(--color-accent)]" : "text-[var(--color-text-secondary)] hover:text-white"
                  )}
                >
                  {t.is_public ? <Globe className="w-3.5 h-3.5" /> : <Lock className="w-3.5 h-3.5" />}
                </button>
                <span className="flex-1 truncate">{t.name}</span>
                {t.category && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#151515] border border-[var(--color-border-main)] text-[var(--color-text-secondary)]">
                    {t.category}
                  </span>
                )}
                {t.is_public && t.use_count > 0 && (
                  <span className="text-[10px] text-[var(--color-text-secondary)]">{t.use_count} uses</span>
                )}
                <button onClick={() => use(t.id, false)} disabled={busyId === t.id} className="text-[var(--color-accent)] hover:underline">
                  Use
                </button>
                <button onClick={() => remove(t.id)} className="text-[var(--color-text-secondary)] hover:text-[var(--color-error)]">
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === 'marketplace' && (
        <>
          {publicTemplates.length === 0 && (
            <div className="text-xs text-[var(--color-text-secondary)]">
              Nothing published yet{category ? ` in "${category}"` : ''} — be the first from "My Templates".
            </div>
          )}
          <div className="space-y-1">
            {publicTemplates.map(t => (
              <div key={t.id} className="flex items-center gap-2 text-xs py-1.5 border-b border-[var(--color-border-main)]/50 last:border-0">
                <Globe className="w-3.5 h-3.5 text-[var(--color-accent)] shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="truncate">{t.name}</div>
                  {t.description && (
                    <div className="text-[10px] text-[var(--color-text-secondary)] truncate">{t.description}</div>
                  )}
                </div>
                {t.category && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#151515] border border-[var(--color-border-main)] text-[var(--color-text-secondary)] shrink-0">
                    {t.category}
                  </span>
                )}
                {t.use_count > 0 && (
                  <span className="text-[10px] text-[var(--color-text-secondary)] shrink-0">{t.use_count} uses</span>
                )}
                <button
                  onClick={() => use(t.id, true)}
                  disabled={busyId === t.id}
                  className="text-[var(--color-accent)] hover:underline shrink-0"
                >
                  {busyId === t.id ? '...' : 'Use'}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function TabButton({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 text-sm font-medium px-2 py-1 rounded-[var(--radius-global)] transition-colors",
        active ? "bg-[var(--color-panel-200)] text-[var(--color-text-primary)]" : "text-[var(--color-text-secondary)] hover:text-white"
      )}
    >
      {icon} {children}
    </button>
  );
}
