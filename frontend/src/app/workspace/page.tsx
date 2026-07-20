'use client';
/**
 * /workspace — Autonomous Workspace Manipulation.
 * Three-pane IDE layout: explorer | editor | agent panel.
 * Patch approval renders as a modal (DiffViewer) on top.
 */
import { useEffect } from 'react';
import { FileTree } from '@/components/workspace/FileTree';
import { EditorPane } from '@/components/workspace/EditorPane';
import { AgentPanel } from '@/components/workspace/AgentPanel';
import { DiffViewer } from '@/components/workspace/DiffViewer';
import { useWorkspaceStore } from '@/stores/workspace';

export default function WorkspacePage() {
  const { fetchTree, fetchPatches, fetchCheckpoints, startLivePolling } = useWorkspaceStore();

  useEffect(() => {
    fetchTree();
    fetchPatches();
    fetchCheckpoints();
    return startLivePolling(); // poll change feed while the page is open
  }, [fetchTree, fetchPatches, fetchCheckpoints, startLivePolling]);

  return (
    <div className="flex h-full min-h-0">
      <div className="w-[260px] shrink-0 border-r border-[var(--color-border-main)] bg-[var(--color-panel-100)]">
        <FileTree />
      </div>
      <div className="flex-1 min-w-0">
        <EditorPane />
      </div>
      <div className="w-[340px] shrink-0 border-l border-[var(--color-border-main)] bg-[var(--color-panel-100)]">
        <AgentPanel />
      </div>
      <DiffViewer />
    </div>
  );
}
