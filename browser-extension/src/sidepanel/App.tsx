/**
 * App.tsx — side panel shell: auth gate, page-context card, tabs
 * (Workflows / Runs / Assistant), and the Ctrl+K command palette.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { CommandPalette, type PaletteCommand } from './components/CommandPalette';
import { WorkflowsView } from './components/WorkflowsView';
import { RunsView } from './components/RunsView';
import { AssistantView } from './components/AssistantView';
import { usePageContext, useSessionOverrides, useSettings, useToken, useWorkflows } from './hooks';
import type { RunDetail } from '../shared/types';

type Tab = 'workflows' | 'runs' | 'assistant';

export function App() {
  const { token, loading: tokenLoading } = useToken();
  const settings = useSettings();
  const { context, capture, clear } = usePageContext();
  const overrides = useSessionOverrides();
  const [tab, setTab] = useState<Tab>('workflows');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [runFocus, setRunFocus] = useState<{ workflowId: string; runId: string | null } | null>(null);
  const [banner, setBanner] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const authed = Boolean(token);
  const { workflows, loading, error, reload } = useWorkflows(authed);

  // Ctrl/Cmd+K opens the palette anywhere in the panel.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen(v => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const doCapture = useCallback(async () => {
    setCaptureError(null);
    const err = await capture();
    if (err) setCaptureError(err);
  }, [capture]);

  const onRunFinished = useCallback((workflowId: string, run: RunDetail | null, error?: string) => {
    if (run) {
      setBanner({ kind: run.status === 'failed' ? 'err' : 'ok', text: `Run ${run.status}` });
      setRunFocus({ workflowId, runId: run.run_id });
      setTab('runs');
    } else if (error) {
      setBanner({ kind: 'err', text: error });
    }
    setTimeout(() => setBanner(null), 4000);
  }, []);

  const paletteCommands = useMemo<PaletteCommand[]>(() => [
    { id: 'capture', title: 'Capture current page', hint: 'Alt+Shift+X', run: () => void doCapture() },
    ...(context ? [{ id: 'clear-ctx', title: 'Clear captured page', run: clear }] : []),
    { id: 'tab-workflows', title: 'Go to Workflows', run: () => setTab('workflows') },
    { id: 'tab-runs', title: 'Go to Runs', run: () => setTab('runs') },
    { id: 'tab-assistant', title: 'Go to Assistant', run: () => setTab('assistant') },
    { id: 'reload', title: 'Refresh workflows', run: reload },
    { id: 'open-app', title: 'Open Xoltra web app', run: () => void chrome.tabs.create({ url: `${settings.webAppUrl}/workflows` }) },
    { id: 'options', title: 'Extension options', run: () => void chrome.runtime.openOptionsPage() },
    ...workflows.map(w => ({
      id: `run-${w.id}`,
      title: `Run: ${w.name}`,
      hint: w.status,
      run: () => { setTab('workflows'); },
    })),
  ], [context, clear, doCapture, reload, settings.webAppUrl, workflows]);

  if (tokenLoading) {
    return <div className="app"><div className="empty"><span className="spinner" style={{ margin: '0 auto' }} /></div></div>;
  }

  return (
    <div className="app">
      <header className="app-header">
        <span className="dot" aria-hidden />
        <span className="brand grow">Xoltra Companion</span>
        <button className="btn btn-ghost tiny" onClick={() => setPaletteOpen(true)} title="Command palette (Ctrl+K)">⌘K</button>
        <button className="btn btn-ghost tiny" onClick={() => void chrome.runtime.openOptionsPage()} title="Options" aria-label="Options">⚙</button>
      </header>

      {!authed ? (
        <div className="empty col" style={{ gap: 10, alignItems: 'center' }}>
          <div>Sign in to connect this browser to Xoltra.</div>
          <button className="btn btn-primary" onClick={() => void chrome.runtime.openOptionsPage()}>
            Open sign-in
          </button>
        </div>
      ) : (
        <>
          {/* Captured page context */}
          <div style={{ padding: '10px 12px 0' }}>
            <div className="card context-card col" style={{ gap: 4 }}>
              {context ? (
                <>
                  <div className="row spread">
                    <span className="small truncate" style={{ fontWeight: 500 }}>{context.title || context.url}</span>
                    <button className="btn btn-ghost tiny" onClick={clear} aria-label="Clear captured context">✕</button>
                  </div>
                  <div className="tiny muted truncate">
                    {context.stats.words.toLocaleString()} words · {context.stats.links} links
                    {context.selection ? ' · has selection' : ''} — sent as trigger data on Run
                  </div>
                </>
              ) : (
                <div className="row spread">
                  <span className="tiny muted">No page captured — workflows run without page context.</span>
                  <button className="btn tiny" onClick={doCapture}>Capture page</button>
                </div>
              )}
              {captureError && <div className="error-box tiny">{captureError}</div>}
            </div>
          </div>

          <nav className="tabs" aria-label="Sections">
            {(['workflows', 'runs', 'assistant'] as const).map(t => (
              <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)} aria-current={tab === t}>
                {t === 'workflows' ? 'Workflows' : t === 'runs' ? 'Runs' : 'Assistant'}
              </button>
            ))}
          </nav>

          {banner && (
            <div style={{ padding: '8px 12px 0' }}>
              <div className={banner.kind === 'err' ? 'error-box' : 'card'} style={banner.kind === 'ok' ? { padding: '8px 10px', fontSize: 11, color: 'var(--color-success)' } : undefined}>
                {banner.text}
              </div>
            </div>
          )}

          <main className="content">
            {tab === 'workflows' && (
              <WorkflowsView
                workflows={workflows}
                loading={loading}
                error={error}
                overrides={overrides}
                pageContext={context}
                webAppUrl={settings.webAppUrl}
                onRunFinished={onRunFinished}
              />
            )}
            {tab === 'runs' && <RunsView workflows={workflows} focus={runFocus} />}
            {tab === 'assistant' && <AssistantView pageContext={context} webAppUrl={settings.webAppUrl} />}
          </main>
        </>
      )}

      <CommandPalette open={paletteOpen} commands={paletteCommands} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
