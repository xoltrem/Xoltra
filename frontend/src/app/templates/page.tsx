'use client';
import { LayoutTemplate, Plus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
export default function TemplatesPage() {
  return (
    <div className="p-6 max-w-5xl mx-auto flex flex-col h-full space-y-6">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-2xl font-semibold mb-1 tracking-tight">Templates</h1>
          <p className="text-[var(--color-text-secondary)] text-sm">Pre-built workflows and agent configurations to get started quickly.</p>
        </div>
        <Button className="bg-[var(--color-panel-200)] text-white hover:bg-[#252525] gap-2 border border-[var(--color-border-main)]">
          <Plus className="w-4 h-4" />
          Submit Template
        </Button>
      </div>
      <div className="flex-1 flex items-center justify-center border border-dashed border-[var(--color-border-main)] rounded-[var(--radius-global)] p-12 text-center">
        <div>
          <div className="w-12 h-12 bg-[var(--color-panel-100)] rounded-full flex items-center justify-center mb-4 mx-auto">
            <LayoutTemplate className="w-6 h-6 text-[var(--color-text-secondary)]" />
          </div>
          <h3 className="text-sm font-medium mb-1">Coming Soon</h3>
          <p className="text-xs text-[var(--color-text-secondary)] max-w-[250px] mx-auto">
            The template gallery is being populated with community workflows.
          </p>
        </div>
      </div>
    </div>
  );
}

