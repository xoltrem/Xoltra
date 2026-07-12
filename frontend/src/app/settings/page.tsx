'use client';
import { useState } from 'react';
import { Settings as SettingsIcon, Sparkles, Key, Bell, Shield, Palette, Building2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { PersonalizationPanel } from '@/components/settings/PersonalizationPanel';
import { SecurityPanel } from '@/components/settings/SecurityPanel';
import { AdminPanel } from '@/components/settings/AdminPanel';
import { OneDrivePanel } from '@/components/settings/OneDrivePanel';
import { NotificationsPanel } from '@/components/settings/NotificationsPanel';

const TABS = [
  { id: 'general', label: 'General', icon: SettingsIcon },
  { id: 'personalization', label: 'AI Personalization', icon: Sparkles },
  { id: 'workspace', label: 'Workspace', icon: Building2 },
  { id: 'api-keys', label: 'API Keys', icon: Key },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'security', label: 'Security', icon: Shield },
  { id: 'appearance', label: 'Appearance', icon: Palette },
];

export default function SettingsPage() {
  const [tab, setTab] = useState('personalization');

  return (
    <div className="flex h-full">
      <div className="w-56 border-r border-[var(--color-border-main)] p-4 shrink-0 overflow-y-auto">
        <h1 className="text-lg font-semibold mb-4 px-1">Settings</h1>
        <div className="space-y-0.5">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "w-full flex items-center gap-2.5 px-3 py-2 text-sm rounded-[var(--radius-global)] transition-colors text-left",
                tab === t.id
                  ? "bg-[var(--color-panel-200)] text-white font-medium"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-panel-200)]/50 hover:text-white"
              )}
            >
              <t.icon className={cn("w-4 h-4", tab === t.id ? "text-[var(--color-accent)]" : "")} />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 max-w-2xl">
        {tab === 'personalization' ? (
          <PersonalizationPanel />
        ) : tab === 'security' ? (
          <SecurityPanel />
        ) : tab === 'notifications' ? (
          <NotificationsPanel />
        ) : tab === 'workspace' ? (
          <div className="space-y-6">
            <AdminPanel />
            <OneDrivePanel />
          </div>
        ) : (
          <div className="flex items-center justify-center h-64 text-sm text-[var(--color-text-secondary)]">
            {TABS.find(t => t.id === tab)?.label} settings — coming soon.
          </div>
        )}
      </div>
    </div>
  );
}
