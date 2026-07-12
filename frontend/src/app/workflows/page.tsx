'use client';
import { useState, useEffect } from 'react';
import { Workflow, Plus, Sparkles, Undo2, Redo2, Brain } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { AIAssistantPanel } from '@/components/workflow/AIAssistantPanel';
import { ThinkingPanel } from '@/components/workflow/ThinkingPanel';
import { RunHistory } from '@/components/workflow/RunHistory';
import { TemplateGallery } from '@/components/workflow/TemplateGallery';
import { useWorkflowCanvasStore } from '@/stores';

export default function WorkflowsPage() {
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [thinkingOpen, setThinkingOpen] = useState(false);
  const { nodes, pushState, undo, redo, canUndo, canRedo } = useWorkflowCanvasStore();

  const handleAcceptNode = (node: any) => {
    // Canvas rendering (React Flow) still TODO, but accepted nodes now flow
    // into the undo/redo-tracked store so that work isn't lost once the
    // canvas is wired up — every accepted node is a pushState().
    pushState({ nodes: [...nodes, { id: crypto.randomUUID(), ...node }], edges: useWorkflowCanvasStore.getState().edges });
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      if (e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); }
      else if (e.key === 'y' || (e.key === 'z' && e.shiftKey)) { e.preventDefault(); redo(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [undo, redo]);

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
          <Button variant="outline" size="icon" disabled={!canUndo()} onClick={undo} title="Undo (Ctrl+Z)">
            <Undo2 className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="icon" disabled={!canRedo()} onClick={redo} title="Redo (Ctrl+Y)">
            <Redo2 className="w-4 h-4" />
          </Button>
          <Button variant="outline" className="gap-2" onClick={() => setThinkingOpen(true)} title="Show live agent thinking + code preview">
            <Brain className="w-4 h-4 text-[var(--color-accent)]" />
            Thinking
          </Button>
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

      <TemplateGallery />

      <RunHistory />

      <AIAssistantPanel
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        onAcceptNode={handleAcceptNode}
      />
      <ThinkingPanel open={thinkingOpen} onClose={() => setThinkingOpen(false)} />
    </div>
  );
}
