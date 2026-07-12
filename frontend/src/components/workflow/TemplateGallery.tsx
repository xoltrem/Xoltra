'use client';
import { useEffect, useState } from 'react';
import { LayoutTemplate, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { getTemplates, instantiateTemplate, deleteTemplate, saveAsTemplate } from '@/lib/api';

export function TemplateGallery({ workflowId, onInstantiated }: { workflowId?: string; onInstantiated?: () => void }) {
  const [templates, setTemplates] = useState<any[]>([]);

  const load = () => getTemplates().then(r => setTemplates(r.templates || [])).catch(() => {});
  useEffect(() => { load(); }, []);

  const saveCurrent = async () => {
    if (!workflowId) return;
    const name = prompt('Template name?');
    if (!name) return;
    await saveAsTemplate(workflowId, name);
    load();
  };

  const use = async (id: string) => {
    await instantiateTemplate(id);
    onInstantiated?.();
  };

  const remove = async (id: string) => {
    await deleteTemplate(id);
    load();
  };

  return (
    <div className="border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-sm font-medium">
          <LayoutTemplate className="w-3.5 h-3.5" /> Templates
        </div>
        {workflowId && (
          <Button size="sm" variant="outline" className="gap-1" onClick={saveCurrent}>
            <Plus className="w-3 h-3" /> Save as template
          </Button>
        )}
      </div>
      {templates.length === 0 && <div className="text-xs text-[var(--color-text-secondary)]">No templates saved yet.</div>}
      <div className="space-y-1">
        {templates.map(t => (
          <div key={t.id} className="flex items-center gap-2 text-xs py-1">
            <span className="flex-1">{t.name}</span>
            <button onClick={() => use(t.id)} className="text-[var(--color-accent)] hover:underline">Use</button>
            <button onClick={() => remove(t.id)} className="text-[var(--color-text-secondary)] hover:text-[var(--color-error)]">
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
