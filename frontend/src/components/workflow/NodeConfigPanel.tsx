'use client';
/**
 * NodeConfigPanel — right-hand drawer for editing a selected node's label and
 * params. Schema-driven from node-params.ts; node types without a schema get
 * a raw JSON editor so nothing is un-configurable.
 *
 * Commit model: fields buffer locally while typing and commit on blur (or
 * Enter for single-line fields). Each commit is one pushState() — one undo
 * entry per edit, not per keystroke — and rides the editor's autosave.
 */
import { useMemo, useState } from 'react';
import { X, SlidersHorizontal, ArrowRightToLine, ArrowLeftToLine, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { schemaFor, type ParamField } from '@/lib/node-params';
import type { NodeDefinition, WorkflowFlowNode } from '@/lib/workflow-graph';

interface NodeConfigPanelProps {
  node: WorkflowFlowNode;
  /** Library definition for this node's type, if known — used for the ports list. */
  definition?: NodeDefinition;
  onChange: (nodeId: string, patch: { label?: string; params?: Record<string, unknown> }) => void;
  onClose: () => void;
}

const inputClass =
  'w-full bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] ' +
  'px-2.5 py-1.5 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)]/60 ' +
  'focus:outline-none focus:border-[var(--color-accent)]/40 transition-colors';

export function NodeConfigPanel({ node, definition, onChange, onClose }: NodeConfigPanelProps) {
  const fields = useMemo(() => schemaFor(node.data.nodeType), [node.data.nodeType]);

  return (
    <aside
      className="w-[300px] shrink-0 flex flex-col border-l border-[var(--color-border-main)] bg-[var(--color-panel-100)]/80 backdrop-blur-sm"
      aria-label={`Configure node ${node.data.label}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-[var(--color-border-main)] shrink-0">
        <SlidersHorizontal className="w-3.5 h-3.5 text-[var(--color-accent)]" />
        <span className="text-xs font-medium text-[var(--color-text-primary)] flex-1 truncate">
          Configure node
        </span>
        <button
          onClick={onClose}
          aria-label="Close configuration panel"
          className="text-[var(--color-text-secondary)] hover:text-white transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
        {/* Label */}
        <Field label="Label">
          <CommittedInput
            key={`${node.id}-label`}
            initial={node.data.label}
            placeholder="Node label"
            onCommit={v => { if (v.trim()) onChange(node.id, { label: v.trim() }); }}
          />
        </Field>

        <div className="text-[10px] font-mono text-[var(--color-text-secondary)] -mt-2">
          {node.data.nodeType}
          {node.data.isAIGenerated && (
            <span className="ml-2 text-[var(--color-ai)]">AI-generated</span>
          )}
        </div>

        {/* Params */}
        {fields === null ? (
          <RawParamsEditor
            key={node.id}
            node={node}
            onCommit={params => onChange(node.id, { params })}
          />
        ) : fields.length === 0 ? (
          <p className="text-[11px] text-[var(--color-text-secondary)] leading-relaxed">
            This node has no parameters — it works entirely from its incoming connections.
          </p>
        ) : (
          fields.map(f => (
            <ParamFieldInput
              key={`${node.id}-${f.key}`}
              field={f}
              value={node.data.params?.[f.key]}
              onCommit={v => onChange(node.id, { params: { ...node.data.params, [f.key]: v } })}
            />
          ))
        )}

        {/* Ports (read-only) */}
        {definition && (definition.inputs.length > 0 || definition.outputs.length > 0) && (
          <div className="pt-3 border-t border-[var(--color-border-main)] space-y-2">
            {definition.inputs.length > 0 && (
              <PortList icon={ArrowRightToLine} title="Inputs" ports={definition.inputs} />
            )}
            {definition.outputs.length > 0 && (
              <PortList icon={ArrowLeftToLine} title="Outputs" ports={definition.outputs} />
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

// ─── Field renderers ─────────────────────────────────────────────────────────

function ParamFieldInput({ field, value, onCommit }: {
  field: ParamField;
  value: unknown;
  onCommit: (v: unknown) => void;
}) {
  const strValue = value == null ? '' : (typeof value === 'string' ? value : JSON.stringify(value, null, 2));

  if (field.type === 'select') {
    return (
      <Field label={field.label} help={field.help} required={field.required}>
        <select
          value={typeof value === 'string' ? value : field.options?.[0]?.value ?? ''}
          onChange={e => onCommit(e.target.value)}
          className={inputClass}
        >
          {field.options?.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </Field>
    );
  }

  if (field.type === 'json') {
    return (
      <Field label={field.label} help={field.help} required={field.required}>
        <JsonInput initial={strValue} placeholder={field.placeholder} onCommit={onCommit} />
      </Field>
    );
  }

  if (field.type === 'number') {
    return (
      <Field label={field.label} help={field.help} required={field.required}>
        <CommittedInput
          initial={strValue}
          placeholder={field.placeholder}
          inputType="number"
          min={field.min}
          max={field.max}
          step={field.step}
          onCommit={v => {
            if (v === '') { onCommit(undefined); return; }
            const n = Number(v);
            if (!Number.isNaN(n)) onCommit(n);
          }}
        />
      </Field>
    );
  }

  // text / textarea / password
  return (
    <Field label={field.label} help={field.help} required={field.required}>
      <CommittedInput
        initial={strValue}
        placeholder={field.placeholder}
        inputType={field.type === 'password' ? 'password' : 'text'}
        multiline={field.type === 'textarea'}
        onCommit={v => onCommit(v === '' ? undefined : v)}
      />
    </Field>
  );
}

/** Input that buffers while typing and commits on blur / Enter. */
function CommittedInput({ initial, placeholder, inputType = 'text', multiline, min, max, step, onCommit }: {
  initial: string;
  placeholder?: string;
  inputType?: 'text' | 'password' | 'number';
  multiline?: boolean;
  min?: number;
  max?: number;
  step?: number;
  onCommit: (v: string) => void;
}) {
  const [val, setVal] = useState(initial);
  // External param updates (e.g. undo) while the same node stays selected:
  // re-seed during render (React's recommended "adjust state on prop change"
  // pattern) instead of an effect, which would double-render. Node switches
  // are handled by the parent's `key=`. `seenInitial` doubles as the
  // last-committed value.
  const [seenInitial, setSeenInitial] = useState(initial);
  if (initial !== seenInitial) {
    setSeenInitial(initial);
    setVal(initial);
  }

  const commit = () => {
    if (val === seenInitial) return;
    setSeenInitial(val);
    onCommit(val);
  };

  if (multiline) {
    return (
      <textarea
        value={val}
        rows={4}
        placeholder={placeholder}
        onChange={e => setVal(e.target.value)}
        onBlur={commit}
        className={cn(inputClass, 'resize-y font-mono leading-relaxed')}
      />
    );
  }
  return (
    <input
      type={inputType}
      value={val}
      min={min}
      max={max}
      step={step}
      placeholder={placeholder}
      onChange={e => setVal(e.target.value)}
      onBlur={commit}
      onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
      className={inputClass}
    />
  );
}

/** JSON field: commits parsed object on blur; invalid JSON shows an error and doesn't commit. */
function JsonInput({ initial, placeholder, onCommit }: {
  initial: string;
  placeholder?: string;
  onCommit: (v: unknown) => void;
}) {
  const [val, setVal] = useState(initial);
  const [error, setError] = useState<string | null>(null);

  // Same render-time re-seed pattern as CommittedInput (see comment there).
  const [seenInitial, setSeenInitial] = useState(initial);
  if (initial !== seenInitial) {
    setSeenInitial(initial);
    setVal(initial);
    setError(null);
  }

  const commit = () => {
    const trimmed = val.trim();
    if (trimmed === '') { setError(null); onCommit(undefined); return; }
    try {
      onCommit(JSON.parse(trimmed));
      setError(null);
    } catch {
      setError('Invalid JSON — not saved');
    }
  };

  return (
    <div>
      <textarea
        value={val}
        rows={4}
        placeholder={placeholder}
        onChange={e => { setVal(e.target.value); if (error) setError(null); }}
        onBlur={commit}
        spellCheck={false}
        className={cn(inputClass, 'resize-y font-mono leading-relaxed', error && 'border-[var(--color-error)]/60')}
      />
      {error && (
        <p className="flex items-center gap-1 mt-1 text-[10px] text-[var(--color-error)]">
          <AlertTriangle className="w-3 h-3" /> {error}
        </p>
      )}
    </div>
  );
}

/** Fallback for node types without a schema: edit the whole params object as JSON. */
function RawParamsEditor({ node, onCommit }: {
  node: WorkflowFlowNode;
  onCommit: (params: Record<string, unknown>) => void;
}) {
  return (
    <Field
      label="Parameters (JSON)"
      help="No schema is registered for this node type — edit its raw params."
    >
      <JsonInput
        initial={Object.keys(node.data.params || {}).length ? JSON.stringify(node.data.params, null, 2) : ''}
        placeholder='{ "key": "value" }'
        onCommit={v => {
          if (v === undefined) { onCommit({}); return; }
          if (v && typeof v === 'object' && !Array.isArray(v)) onCommit(v as Record<string, unknown>);
        }}
      />
    </Field>
  );
}

// ─── Layout bits ─────────────────────────────────────────────────────────────

function Field({ label, help, required, children }: {
  label: string;
  help?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-[10px] uppercase tracking-wider font-medium text-[var(--color-text-secondary)] mb-1">
        {label}{required && <span className="text-[var(--color-accent)] ml-0.5">*</span>}
      </span>
      {children}
      {help && <p className="mt-1 text-[10px] text-[var(--color-text-secondary)]/80 leading-relaxed">{help}</p>}
    </label>
  );
}

function PortList({ icon: Icon, title, ports }: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  ports: { name: string; type: string }[];
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-medium text-[var(--color-text-secondary)] mb-1">
        <Icon className="w-3 h-3" /> {title}
      </div>
      <div className="space-y-0.5">
        {ports.map(p => (
          <div key={p.name} className="flex items-center gap-2 text-[11px]">
            <span className="text-[var(--color-text-primary)] font-mono">{p.name}</span>
            <span className="text-[var(--color-text-secondary)]">{p.type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
