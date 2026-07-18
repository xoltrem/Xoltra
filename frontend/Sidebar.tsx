'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  Workflow,
  Settings,
  BookOpen,
  ShieldAlert,
  LayoutTemplate,
  Users,
  Wrench,
  Search,
  MonitorPlay,
  CreditCard,
  FolderKanban
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTermsStore, useUIStore } from '@/stores';

const NAV_ITEMS = [
  { label: 'Dashboard', icon: Activity, href: '/', requiresConsent: true },
  { label: 'Projects', icon: FolderKanban, href: '/projects', requiresConsent: true },
  { label: 'Workflows', icon: Workflow, href: '/workflows', requiresConsent: true },
  { label: 'Templates', icon: LayoutTemplate, href: '/templates', requiresConsent: true },
  { label: 'Tools & Plugins', icon: Wrench, href: '/tools', requiresConsent: true },
  { label: 'Agents', icon: Users, href: '/agents', requiresConsent: true },
  { label: 'Knowledge', icon: BookOpen, href: '/knowledge', requiresConsent: true },
  { label: 'Executions', icon: Activity, href: '/executions', requiresConsent: true },
  { label: 'Audit Logs', icon: ShieldAlert, href: '/audit', requiresConsent: true },
  { label: 'Pricing', icon: CreditCard, href: '/pricing' },
];

const BOTTOM_ITEMS = [
  { label: 'Settings', icon: Settings, href: '/settings' },
];

export function Sidebar() {
  const pathname = usePathname();
  const { setSearchOpen } = useUIStore();
  const termsStatus = useTermsStore((state) => state.status);
  const unityConnected = false; // TODO: Wire to real unity connection status once backend simulation engine is attached

  return (
    <aside className="w-[240px] flex-shrink-0 bg-[var(--color-panel-100)] border-r border-[var(--color-border-main)] flex flex-col h-full overflow-hidden">
      <div className="h-14 flex items-center px-4 border-b border-[var(--color-border-main)] shrink-0 gap-2">
        <div className="font-[var(--font-tiempo)] text-lg font-bold tracking-wide text-white">Xoltra</div>
        <div className="text-[10px] bg-[var(--color-accent)]/10 text-[var(--color-accent)] border border-[var(--color-accent)]/20 px-1.5 py-0.5 rounded font-mono font-medium ml-auto">
          v2.1
        </div>
      </div>

      <div className="p-3">
        <button
          onClick={() => setSearchOpen(true)}
          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-[var(--color-text-secondary)] bg-[#151515] hover:bg-[#1a1a1a] border border-[var(--color-border-main)] rounded-[var(--radius-global)] transition-colors"
        >
          <Search className="w-4 h-4" />
          <span className="flex-1 text-left">Search...</span>
          <kbd className="hidden sm:inline-flex h-5 items-center gap-1 rounded bg-[#202020] px-1.5 font-mono text-[10px] font-medium text-[var(--color-text-secondary)]">
            <span>⌘</span>K
          </kbd>
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto p-3 pt-0 space-y-1">
        {NAV_ITEMS.filter((item) => !item.requiresConsent || termsStatus === 'accepted').map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 text-sm rounded-[var(--radius-global)] transition-colors",
                isActive
                  ? "bg-[var(--color-panel-200)] text-white font-medium shadow-sm border border-[var(--color-border-hover)]"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-panel-200)]/50 hover:text-white"
              )}
            >
              <item.icon className={cn("w-4 h-4", isActive ? "text-[var(--color-accent)]" : "")} />
              {item.label}
            </Link>
          )
        })}
      </nav>

      <div className="p-3 border-t border-[var(--color-border-main)] space-y-1 shrink-0">
        {BOTTOM_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 text-sm rounded-[var(--radius-global)] transition-colors",
                isActive
                  ? "bg-[var(--color-panel-200)] text-white font-medium shadow-sm border border-[var(--color-border-hover)]"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-panel-200)]/50 hover:text-white"
              )}
            >
              <item.icon className={cn("w-4 h-4", isActive ? "text-[var(--color-accent)]" : "")} />
              {item.label}
            </Link>
          )
        })}

        <div className="mt-4 pt-3 flex items-center gap-2 px-3 text-xs text-[var(--color-text-secondary)]">
          <MonitorPlay className="w-3.5 h-3.5" />
          <span>Unity Viewport</span>
          <div className={cn(
            "w-2 h-2 rounded-full ml-auto",
            unityConnected ? "bg-[var(--color-success)] shadow-[0_0_8px_var(--color-success)]" : "bg-[var(--color-border-hover)]"
          )} title={unityConnected ? "Connected" : "Disconnected"} />
        </div>
      </div>
    </aside>
  );
}
