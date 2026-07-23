'use client';
import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { cn } from '@/lib/utils';
import { Play, FileText, Database, Server, Cpu, Box } from 'lucide-react';
import type { WorkflowFlowNode } from '@/lib/workflow-graph';
// PRD Node Categories mapped to colors
const CATEGORY_COLORS: Record<string, string> = {
  trigger: 'border-l-[var(--color-accent)]',
  ai: 'border-l-[var(--color-ai)]',
  integration: 'border-l-[var(--color-success)]',
  database: 'border-l-[var(--color-success)]',
  storage: 'border-l-[var(--color-success)]',
  logic: 'border-l-[var(--color-warning)]',
  utility: 'border-l-[var(--color-warning)]',
  system: 'border-l-[var(--color-warning)]',
};
const CATEGORY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  trigger: Play,
  ai: Cpu,
  integration: Box,
  database: Database,
  storage: Server,
  logic: FileText,
};
export const CustomNode = memo(function CustomNode({ data, isConnectable, selected }: NodeProps<WorkflowFlowNode>) {
  const category = String(data.category || 'utility').toLowerCase();
  const isAIGenerated = data.isAIGenerated === true;
  
  const borderColorClass = CATEGORY_COLORS[category] || 'border-l-[var(--color-border-main)]';
  const Icon = CATEGORY_ICONS[category] || Box;
  return (
    <div className={cn(
      "w-[240px] bg-[var(--color-panel-100)] rounded-[var(--radius-global)] text-left flex flex-col relative",
      "border border-[var(--color-border-main)] shadow-sm transition-all",
      borderColorClass,
      "border-l-4", // Thick left border per PRD
      isAIGenerated ? "border-l-dashed" : "border-l-solid",
      selected ? "ring-1 ring-[var(--color-accent)] shadow-[0_0_8px_var(--color-accent)]/20" : ""
    )}>
      {/* Target handle for incoming connections */}
      {category !== 'trigger' && (
        <Handle 
          type="target" 
          position={Position.Left} 
          isConnectable={isConnectable}
          className="w-2 h-2 bg-[var(--color-border-main)] border-none rounded-full -ml-1"
        />
      )}
      <div className="p-3 flex items-center gap-3 border-b border-[var(--color-border-main)] bg-black/20">
        <div className="w-6 h-6 rounded bg-[#151515] flex items-center justify-center shrink-0 border border-[var(--color-border-main)]">
          <Icon className="w-3.5 h-3.5 text-[var(--color-text-secondary)]" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-[var(--color-text-primary)] truncate">
            {data.label || 'Node'}
          </div>
          <div className="text-[10px] text-[var(--color-text-secondary)] uppercase tracking-wider font-medium truncate">
            {data.action || category}
          </div>
        </div>
      </div>
      <div className="p-3 text-xs text-[var(--color-text-secondary)] leading-relaxed">
        {data.description || 'No description provided.'}
      </div>
      {/* Source handle for outgoing connections */}
      <Handle
        type="source"
        position={Position.Right}
        isConnectable={isConnectable}
        className="w-2 h-2 bg-[var(--color-accent)] border-none rounded-full -mr-1"
      />
    </div>
  );
});
