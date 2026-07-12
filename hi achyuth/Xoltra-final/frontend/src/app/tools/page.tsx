'use client';
import { useState } from 'react';
import { Wrench, Plug, Package, Search, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';

// ─── Data ─────────────────────────────────────────────────────────────────
// TODO: replace with GET /api/tools once the backend tool registry exists

interface ToolItem {
  id: string;
  name: string;
  description: string;
  category: 'native' | 'integration' | 'addon';
  icon: typeof Wrench;
  enabled: boolean;
  scopes?: string[];
}

const NATIVE_TOOLS: ToolItem[] = [
  { id: 'file_ops', name: 'File Operations', description: 'Read, write, and move files within approved directories.', category: 'native', icon: Wrench, enabled: true, scopes: ['~/Documents', '~/Downloads'] },
  { id: 'http_request', name: 'HTTP Request', description: 'Make authenticated calls to external APIs.', category: 'native', icon: Wrench, enabled: true },
  { id: 'transform', name: 'Data Transform', description: 'Apply templates and reshape data between nodes.', category: 'native', icon: Wrench, enabled: true },
];

const INTEGRATIONS: ToolItem[] = [
  { id: 'gmail', name: 'Gmail', description: 'Send and read email on your behalf.', category: 'integration', icon: Plug, enabled: true, scopes: ['send', 'read'] },
  { id: 'slack', name: 'Slack', description: 'Post messages and read channels.', category: 'integration', icon: Plug, enabled: false },
  { id: 'dropbox', name: 'Dropbox', description: 'Upload and organize files.', category: 'integration', icon: Plug, enabled: false },
  { id: 'spotify', name: 'Spotify', description: 'Manage playlists and playback.', category: 'integration', icon: Plug, enabled: false },
];

const ADDONS: ToolItem[] = [
  { id: 'pdf_ocr', name: 'PDF OCR', description: 'Extract text from scanned PDF documents.', category: 'addon', icon: Package, enabled: false },
  { id: 'sql_connector', name: 'SQL Connector', description: 'Query external SQL databases directly from a node.', category: 'addon', icon: Package, enabled: false },
  { id: 'image_gen', name: 'Image Generation', description: 'Generate images as part of a workflow step.', category: 'addon', icon: Package, enabled: false },
];

// ─── Toggle ───────────────────────────────────────────────────────────────

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative w-9 h-5 rounded-full transition-colors shrink-0",
        checked ? "bg-[var(--color-success)]" : "bg-[var(--color-panel-200)] border border-[var(--color-border-main)]"
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform",
          checked ? "translate-x-[18px]" : "translate-x-0.5"
        )}
      />
    </button>
  );
}

// ─── Tool row ─────────────────────────────────────────────────────────────

function ToolRow({ tool, onToggle }: { tool: ToolItem; onToggle: (id: string, v: boolean) => void }) {
  const Icon = tool.icon;
  return (
    <div className="flex flex-col items-center text-center gap-2 p-3 border border-[var(--color-border-main)] rounded-[var(--radius-global)] bg-[var(--color-panel-100)] hover:border-[var(--color-border-hover)] transition-colors">
      <div className="w-8 h-8 rounded bg-[#151515] flex items-center justify-center shrink-0 border border-[var(--color-border-main)]">
        <Icon className="w-4 h-4 text-[var(--color-text-secondary)]" />
      </div>
      <div className="flex-1 min-w-0 w-full">
        <div className="text-sm font-medium text-[var(--color-text-primary)]">{tool.name}</div>
        <div className="text-xs text-[var(--color-text-secondary)] truncate">{tool.description}</div>
        {tool.scopes && (
          <div className="flex justify-center gap-1 mt-1.5">
            {tool.scopes.map(s => (
              <span key={s} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#151515] border border-[var(--color-border-main)] text-[var(--color-text-secondary)]">
                {s}
              </span>
            ))}
          </div>
        )}
      </div>
      <Toggle checked={tool.enabled} onChange={(v) => onToggle(tool.id, v)} />
    </div>
  );
}

// ─── Section ──────────────────────────────────────────────────────────────

function ToolSection({ title, subtitle, tools, onToggle }: {
  title: string; subtitle: string; tools: ToolItem[]; onToggle: (id: string, v: boolean) => void;
}) {
  return (
    <div>
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">{title}</h2>
        <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">{subtitle}</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {tools.map(t => <ToolRow key={t.id} tool={t} onToggle={onToggle} />)}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────

export default function ToolsPage() {
  const [native, setNative] = useState(NATIVE_TOOLS);
  const [integrations, setIntegrations] = useState(INTEGRATIONS);
  const [addons, setAddons] = useState(ADDONS);
  const [query, setQuery] = useState('');

  const makeToggle = (setter: typeof setNative) => (id: string, v: boolean) => {
    setter(prev => prev.map(t => t.id === id ? { ...t, enabled: v } : t));
    // TODO: POST /api/tools/{id}/toggle  { enabled: v }
    // Backend should route this through permission_bridge.AppRegistry —
    // enabling a tool here should be equivalent to approving it in the App Registry.
  };

  const filterFn = (t: ToolItem) => t.name.toLowerCase().includes(query.toLowerCase());

  return (
    <div className="p-6 max-w-5xl mx-auto flex flex-col h-full space-y-6">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-2xl font-semibold mb-1 tracking-tight">Tools & Plugins</h1>
          <p className="text-[var(--color-text-secondary)] text-sm">
            Native tools, connected integrations, and add-ons your workflows can use.
          </p>
        </div>
        <a
          href="#"
          className="flex items-center gap-2 px-3 py-2 text-sm text-[var(--color-text-secondary)] bg-[var(--color-panel-200)] hover:bg-[#252525] border border-[var(--color-border-main)] rounded-[var(--radius-global)] transition-colors"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          Browse Marketplace
        </a>
      </div>

      <div className="relative shrink-0">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-secondary)]" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search tools, integrations, and add-ons..."
          className="w-full bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] pl-9 pr-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-accent)]/40"
        />
      </div>

      <div className="flex-1 overflow-y-auto space-y-8 pb-6">
        <ToolSection
          title="Native Tools"
          subtitle="Built into Xoltra — no external connection required."
          tools={native.filter(filterFn)}
          onToggle={makeToggle(setNative)}
        />
        <ToolSection
          title="Connected Integrations"
          subtitle="Third-party services your workflows can act on, gated by the Permission Bridge."
          tools={integrations.filter(filterFn)}
          onToggle={makeToggle(setIntegrations)}
        />
        <ToolSection
          title="Add-ons"
          subtitle="Optional capabilities you can enable as needed."
          tools={addons.filter(filterFn)}
          onToggle={makeToggle(setAddons)}
        />
      </div>
    </div>
  );
}
