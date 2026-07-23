'use client';
/**
 * AgentPanel.tsx — instruction input + streaming progress + operation log
 * + patch history + checkpoint rollback. Right-hand column of the page.
 */
import { useState } from 'react';
import {
  Bot, Square, Loader2, CheckCircle2, XCircle, History,
  FileDiff, Undo2, Terminal as TerminalIcon, GitBranch,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWorkspaceStore } from '@/stores/workspace';
import { runTerminal, gitCommit, gitPush } from '@/lib/workspaceApi';

const STEP_LABELS: Record<string, string> = {
  index: 'Indexing repository',
  plan: 'Planning',
  generate: 'Generating code',
  validate: 'Validating',
  apply: 'Applying',
};

export function AgentPanel() {
  const {
    agentRunning, agentSteps, runAgent, stopAgent,
    patches, openPatch, checkpoints, logs, log, fetchTree, fetchCheckpoints,
  } = useWorkspaceStore();
  const [instruction, setInstruction] = useState('');
  const [terminalCmd, setTerminalCmd] = useState('');
  const [tab, setTab] = useState<'agent' | 'terminal' | 'history'>('agent');

  const submit = () => {
    const text = instruction.trim();
    if (!text || agentRunning) return;
    runAgent(text);
    setInstruction('');
  };

  const execTerminal = async () => {
    const cmd = terminalCmd.trim();
    if (!cmd) return;
    setTerminalCmd('');
    log('info', `$ ${cmd}`);
    try {
      const data = await runTerminal(cmd);
      const r = data.result;
      if (r.stdout) log('info', r.stdout.trim());
      if (r.stderr) log(r.ok ? 'warn' : 'error', r.stderr.trim());
      log(r.ok ? 'success' : 'error', `exit ${r.exit_code}`);
      fetchTree();
    } catch (e) { log('error', (e as Error).message); }
  };

  const quickCommitPush = async () => {
    const message = window.prompt('Commit message:');
    if (!message) return;
    try {
      log('info', 'git add -A && git commit…');
      const c = await gitCommit(message);
      log(c.result.ok ? 'success' : 'error', c.result.stdout || c.result.stderr);
      if (!c.result.ok) return;
      log('info', 'git push…');
      const p = await gitPush();
      log(p.result.ok ? 'success' : 'error', p.result.stdout || p.result.stderr || 'pushed');
    } catch (e) { log('error', (e as Error).message); }
  };

  return (
    <div className="flex flex-col h-full">
      {/* tabs */}
      <div className="flex border-b border-[var(--color-border-main)] shrink-0">
        {([['agent', Bot], ['terminal', TerminalIcon], ['history', History]] as const).map(([t, Icon]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 py-2 text-xs capitalize',
              tab === t ? 'text-white border-b-2 border-[var(--color-accent)]' : 'text-[var(--color-text-secondary)] hover:text-white',
            )}
          >
            <Icon className="w-3.5 h-3.5" /> {t}
          </button>
        ))}
      </div>

      {tab === 'agent' && (
        <>
          {/* instruction input */}
          <div className="p-3 border-b border-[var(--color-border-main)] shrink-0">
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
              placeholder="Describe a change… e.g. 'Rename utils.ts to helpers.ts and update all imports'"
              rows={3}
              disabled={agentRunning}
              className="w-full resize-none bg-[#151515] border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-2 text-[13px] text-white outline-none focus:border-[var(--color-accent)]/50"
            />
            <div className="flex justify-end mt-2">
              {agentRunning ? (
                <button onClick={stopAgent}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-[var(--radius-global)] border border-red-400/40 text-red-400 hover:bg-red-950/40">
                  <Square className="w-3 h-3" /> Stop
                </button>
              ) : (
                <button onClick={submit} disabled={!instruction.trim()}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-[var(--radius-global)] bg-[var(--color-accent)] text-black font-medium disabled:opacity-40 hover:opacity-90">
                  <Bot className="w-3.5 h-3.5" /> Run agent
                </button>
              )}
            </div>
          </div>

          {/* streaming steps */}
          <div className="p-3 space-y-2 border-b border-[var(--color-border-main)] shrink-0">
            {agentSteps.length === 0 && !agentRunning && (
              <div className="text-xs text-[var(--color-text-secondary)]">
                The agent plans, generates, and validates a patch. Nothing is applied until you approve the diff.
              </div>
            )}
            {agentSteps.map((s, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                {s.error ? <XCircle className="w-3.5 h-3.5 text-red-400 mt-0.5 shrink-0" />
                  : s.done ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
                  : <Loader2 className="w-3.5 h-3.5 text-[var(--color-accent)] animate-spin mt-0.5 shrink-0" />}
                <div className="min-w-0">
                  <span className="text-white">{STEP_LABELS[s.step] ?? s.step}</span>
                  <span className="text-[var(--color-text-secondary)]"> — {s.detail}</span>
                  {s.reasoning && <div className="text-[var(--color-text-secondary)] italic mt-0.5">{s.reasoning}</div>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === 'terminal' && (
        <div className="p-3 border-b border-[var(--color-border-main)] shrink-0 space-y-2">
          <div className="flex gap-2">
            <input
              value={terminalCmd}
              onChange={(e) => setTerminalCmd(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') execTerminal(); }}
              placeholder="git status · npm run lint · pytest …"
              className="flex-1 bg-[#151515] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-2 py-1.5 text-[13px] font-mono text-white outline-none focus:border-[var(--color-accent)]/50"
            />
            <button onClick={execTerminal}
              className="px-3 py-1.5 text-xs rounded-[var(--radius-global)] bg-[var(--color-panel-200)] text-white hover:bg-[var(--color-border-hover)]">
              Run
            </button>
          </div>
          <button onClick={quickCommitPush}
            className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs rounded-[var(--radius-global)] border border-[var(--color-border-main)] text-white hover:bg-[var(--color-panel-200)]">
            <GitBranch className="w-3.5 h-3.5" /> Commit &amp; push
          </button>
          <div className="text-[11px] text-[var(--color-text-secondary)]">
            Allowlisted commands only, sandboxed to the workspace root.
          </div>
        </div>
      )}

      {tab === 'history' && (
        <div className="border-b border-[var(--color-border-main)] shrink-0 max-h-[40%] overflow-y-auto">
          <div className="px-3 pt-3 pb-1 text-[11px] uppercase tracking-wide text-[var(--color-text-secondary)]">Patches</div>
          {patches.length === 0 && <div className="px-3 pb-2 text-xs text-[var(--color-text-secondary)]">None yet.</div>}
          {patches.map((p) => (
            <button key={p.id} onClick={() => openPatch(p.id)}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left hover:bg-[var(--color-panel-200)]/50">
              <FileDiff className="w-3.5 h-3.5 shrink-0 text-[var(--color-accent)]" />
              <span className="flex-1 truncate text-white">{p.title}</span>
              <span className={cn('font-mono text-[10px]',
                p.status === 'applied' ? 'text-emerald-400'
                  : p.status === 'proposed' ? 'text-amber-400'
                  : 'text-[var(--color-text-secondary)]')}>
                {p.status}
              </span>
            </button>
          ))}
          <div className="px-3 pt-3 pb-1 text-[11px] uppercase tracking-wide text-[var(--color-text-secondary)]">Checkpoints</div>
          {checkpoints.map((c) => (
            <div key={c.id} className="flex items-center gap-2 px-3 py-1.5 text-xs">
              <Undo2 className="w-3.5 h-3.5 shrink-0 text-[var(--color-text-secondary)]" />
              <span className="flex-1 truncate text-[var(--color-text-secondary)]">{c.label || c.id}</span>
              <span className="font-mono text-[10px] text-[var(--color-text-secondary)]">{c.files} file{c.files === 1 ? '' : 's'}</span>
            </div>
          ))}
        </div>
      )}

      {/* operation log — always visible */}
      <div className="flex-1 overflow-y-auto p-3 font-mono text-[11px] leading-4 space-y-0.5">
        {logs.map((l, i) => (
          <div key={i} className={cn(
            l.level === 'error' ? 'text-red-400'
              : l.level === 'warn' ? 'text-amber-400'
              : l.level === 'success' ? 'text-emerald-400'
              : 'text-[var(--color-text-secondary)]',
          )}>
            <span className="opacity-50">{new Date(l.ts).toLocaleTimeString()} </span>
            {l.text}
          </div>
        ))}
      </div>
    </div>
  );
}
