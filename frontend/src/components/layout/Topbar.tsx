'use client';
import { useSystemStore, useTermsStore } from '@/stores';
import { Play, Pause, Square, AlertCircle, Bell } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { agentAction } from '@/lib/api';
import { NotifyToggle } from '@/components/ui/NotifyToggle';
export function Topbar() {
  const { status } = useSystemStore();
  const termsStatus = useTermsStore((state) => state.status);
  
  const agentState = String(status?.status ?? 'OFFLINE');
  
  const handleAction = async (action: 'start' | 'pause' | 'resume' | 'stop') => {
    try {
      await agentAction(action);
      // Let the polling in the root layout catch the state change
    } catch (e) {
      console.error(e);
    }
  };
  const getStatusColor = () => {
    switch (agentState) {
      case 'RUNNING': return 'bg-[var(--color-success)]';
      case 'PAUSED': return 'bg-[var(--color-warning)]';
      case 'OFFLINE': 
      case 'ERROR': return 'bg-[var(--color-error)]';
      default: return 'bg-[var(--color-text-secondary)]';
    }
  };
  return (
    <header className="h-14 border-b border-[var(--color-border-main)] bg-[var(--color-panel-100)] flex items-center justify-between px-4 shrink-0">
      <div className="flex items-center gap-4">
        {/* Breadcrumb or context title can go here */}
      </div>
      <div className="flex items-center gap-3">
        {termsStatus === 'rejected' ? (
          <span className="text-xs text-[var(--color-text-secondary)]">Limited access until Terms are accepted</span>
        ) : <>
        {/* Agent Controls */}
        <div className="flex items-center bg-[#151515] border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-1 gap-1">
          <div className="flex items-center gap-2 px-3 border-r border-[var(--color-border-main)]">
            <div className={`w-2 h-2 rounded-full ${getStatusColor()} shadow-[0_0_8px_currentColor] opacity-80`} />
            <span className="text-xs font-mono text-[var(--color-text-primary)] font-medium tracking-wide">
              {agentState}
            </span>
          </div>
          
          <div className="flex px-1 gap-1">
            {(agentState === 'IDLE' || agentState === 'PAUSED' || agentState === 'OFFLINE') && (
              <Button 
                variant="ghost" 
                size="sm" 
                className="h-7 px-2 text-[var(--color-success)] hover:text-[var(--color-success)] hover:bg-[var(--color-success)]/10"
                onClick={() => handleAction(agentState === 'PAUSED' ? 'resume' : 'start')}
              >
                <Play className="w-3.5 h-3.5 mr-1" />
                {agentState === 'PAUSED' ? 'Resume' : 'Start'}
              </Button>
            )}
            
            {agentState === 'RUNNING' && (
              <>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-7 px-2 text-[var(--color-warning)] hover:text-[var(--color-warning)] hover:bg-[var(--color-warning)]/10"
                  onClick={() => handleAction('pause')}
                >
                  <Pause className="w-3.5 h-3.5 mr-1" />
                  Pause
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-7 px-2 text-[var(--color-error)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/10"
                  onClick={() => handleAction('stop')}
                >
                  <Square className="w-3.5 h-3.5 mr-1" />
                  Stop
                </Button>
              </>
            )}
          </div>
        </div>
        {/* Notifications */}
        <NotifyToggle />
        <div className="relative group">
          <Button variant="ghost" size="icon" className="h-9 w-9 text-[var(--color-text-secondary)] hover:text-white">
            <Bell className="w-4 h-4" />
            <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]" />
          </Button>
          
          <div className="absolute top-full right-0 mt-2 w-80 bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] shadow-xl hidden group-hover:flex group-focus-within:flex flex-col z-50">
            <div className="p-3 border-b border-[var(--color-border-main)] flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">Notifications</span>
              <button className="text-[10px] text-[var(--color-accent)] hover:underline">Mark all read</button>
            </div>
            <div className="max-h-64 overflow-y-auto">
              <div className="p-3 border-b border-[var(--color-border-main)] hover:bg-[#1a1a1a] transition-colors">
                <div className="text-sm font-medium text-[var(--color-text-primary)] mb-1">Workflow Failed</div>
                <div className="text-xs text-[var(--color-text-secondary)]">The "Daily Sync" workflow failed at the "Post to Slack" node.</div>
                <div className="text-[10px] text-[var(--color-text-secondary)] mt-2">10 minutes ago</div>
              </div>
              <div className="p-3 hover:bg-[#1a1a1a] transition-colors">
                <div className="text-sm font-medium text-[var(--color-text-primary)] mb-1">New Agent Discovered</div>
                <div className="text-xs text-[var(--color-text-secondary)]">ResearchAgent.role was loaded from the directory.</div>
                <div className="text-[10px] text-[var(--color-text-secondary)] mt-2">1 hour ago</div>
              </div>
            </div>
          </div>
        </div>
        </>}
      </div>
    </header>
  );
}
