'use client';
import { useState } from 'react';
import { Workflow, Plus, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { AIAssistantPanel } from '@/components/workflow/AIAssistantPanel';

export default function WorkflowsPage() {
  const [assistantOpen, setAssistantOpen] = useState(false);

  const handleAcceptNode = (node: any) => {
    // TODO: push the accepted node onto the React Flow canvas state
    // once the canvas itself is wired up (React Flow + Zustand node store).
    console.log('Node accepted onto canvas:', node);
  };

  return (
    <div className="p-6 max-w-5xl mx-auto flex flex-col h-full space-y-6">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-2xl font-semibold mb-1 tracking-tight">Workflows</h1>
          <p className="text-[var(--color-text-secondary)] text-sm">
            Build automations by hand or describe them to the assistant.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => setAssistantOpen(true)}
          >
            <Sparkles className="w-4 h-4 text-[var(--color-accent)]" />
            Ask Assistant
          </Button>
          <Button className="gap-2" onClick={() => setAssistantOpen(true)}>
            <Plus className="w-4 h-4" />
            Create Workflow
          </Button>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center border border-dashed border-[var(--color-border-main)] rounded-[var(--radius-global)] p-12 text-center">
        <div>
          <div className="w-12 h-12 bg-[var(--color-panel-100)] rounded-full flex items-center justify-center mb-4 mx-auto">
            <Workflow className="w-6 h-6 text-[var(--color-text-secondary)]" />
          </div>
          <h3 className="text-sm font-medium mb-1">No workflows yet</h3>
          <p className="text-xs text-[var(--color-text-secondary)] max-w-[280px] mx-auto mb-4">
            Click "Create Workflow" and describe what you want automated — the assistant builds it with you.
          </p>
          <Button size="sm" onClick={() => setAssistantOpen(true)} className="gap-2">
            <Sparkles className="w-3.5 h-3.5" />
            Start with the assistant
          </Button>
        </div>
      </div>

      <AIAssistantPanel
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        onAcceptNode={handleAcceptNode}
      />
    </div>
  );
}
