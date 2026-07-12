/**
 * Xoltra Dashboard — React UI
 * Polls /status every 1.5s. Connects to Xoltra agent on :4000.
 *
 * Standalone React app. In /dashboard/, run:
 *   npm create vite@latest . -- --template react
 *   replace src/App.jsx with this file
 *   npm run dev
 */

import { useState, useEffect, useRef, useCallback } from 'react';

const API = import.meta.env?.VITE_API_URL || 'http://localhost:4000';

// ── Constants ─────────────────────────────────────────────────────────────────

const AgentStatus = { IDLE: 'IDLE', RUNNING: 'RUNNING', PAUSED: 'PAUSED', RESUMING: 'RESUMING', OFFLINE: 'OFFLINE', ERROR: 'ERROR' };
const TaskStatus  = { PENDING: 'PENDING', RUNNING: 'RUNNING', PAUSED: 'PAUSED', DONE: 'DONE', FAILED: 'FAILED' };

const CONNECTOR_META = {
  gmail       : { icon: '📧', color: '#ea4335', category: 'Communication' },
  word        : { icon: '📝', color: '#2b579a', category: 'Office'        },
  browser     : { icon: '🌐', color: '#4285f4', category: 'Web'           },
  codex       : { icon: '💻', color: '#00b4d8', category: 'IDE'           },
  antigravity : { icon: '🚀', color: '#7c3aed', category: 'IDE'           },
  workflow    : { icon: '⚙️', color: '#10b981', category: 'Automation'    },
};

// ── API helpers ───────────────────────────────────────────────────────────────

const call = async (method, path, body) => {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  return res.json();
};

// ── Style tokens ──────────────────────────────────────────────────────────────

const C = {
  bg       : '#09090b',
  surface  : '#111113',
  border   : '#27272a',
  accent   : '#6c63ff',
  success  : '#10b981',
  warning  : '#f59e0b',
  danger   : '#ef4444',
  text     : '#e4e4e7',
  muted    : '#71717a',
  dimmer   : '#3f3f46',
};

const taskColor = s => ({ RUNNING: '#3b82f6', PENDING: C.warning, PAUSED: C.muted, DONE: C.success, FAILED: C.danger }[s] || C.muted);
const agentColor = s => ({ RUNNING: C.success, IDLE: C.muted, PAUSED: C.warning, RESUMING: '#3b82f6', OFFLINE: C.danger, ERROR: C.danger }[s] || C.muted);

const S = {
  root    : { fontFamily: "'Inter',system-ui,sans-serif", background: C.bg, color: C.text, minHeight: '100vh', display: 'flex', flexDirection: 'column', fontSize: 13 },
  topbar  : { background: C.surface, borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', padding: '0 18px', height: 52, gap: 10, flexShrink: 0 },
  logo    : { fontWeight: 800, fontSize: 18, letterSpacing: -1, color: '#fff' },
  chip    : (bg, fg) => ({ background: bg, color: fg, padding: '3px 9px', borderRadius: 20, fontSize: 11, fontWeight: 700 }),
  layout  : { display: 'flex', flex: 1, overflow: 'hidden' },
  sidebar : { width: 192, background: C.surface, borderRight: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', padding: '12px 8px', gap: 2, flexShrink: 0 },
  navItem : active => ({ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', borderRadius: 7, cursor: 'pointer', background: active ? C.accent + '25' : 'transparent', color: active ? '#a78bfa' : C.muted, fontWeight: active ? 600 : 400, fontSize: 13, userSelect: 'none' }),
  main    : { flex: 1, overflow: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 14 },
  card    : { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: 16 },
  grid    : cols => ({ display: 'grid', gridTemplateColumns: `repeat(${cols},1fr)`, gap: 12 }),
  badge   : (c) => ({ background: c + '22', color: c, padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700 }),
  tag     : { background: '#18181b', border: `1px solid ${C.border}`, color: C.muted, padding: '2px 7px', borderRadius: 4, fontSize: 11 },
  btn     : (v='default') => ({
    padding: '6px 14px', borderRadius: 7, fontSize: 12, fontWeight: 600,
    cursor: 'pointer', border: 'none', outline: 'none',
    background: v==='primary'?C.accent: v==='success'?C.success: v==='danger'?C.danger: '#27272a',
    color: '#fff', transition: 'opacity .15s',
  }),
  input   : { background: '#18181b', border: `1px solid ${C.border}`, color: C.text, borderRadius: 7, padding: '7px 10px', fontSize: 12, outline: 'none' },
  dot     : c => ({ width: 8, height: 8, borderRadius: '50%', background: c, flexShrink: 0 }),
  label   : { fontSize: 11, fontWeight: 600, color: C.muted, textTransform: 'uppercase', letterSpacing: .5, marginBottom: 10 },
  divider : { height: 1, background: C.border, margin: '6px 0' },
  mono    : { fontFamily: 'monospace', fontSize: 11 },
};

// ── Micro components ──────────────────────────────────────────────────────────

function ProgressBar({ pct, color = C.accent }) {
  return (
    <div style={{ height: 4, background: C.border, borderRadius: 2, overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 2, transition: 'width .4s ease' }} />
    </div>
  );
}

function Dot({ color }) { return <div style={S.dot(color)} />; }

function TimeAgo({ ts }) {
  if (!ts) return null;
  const diff = Date.now() - ts;
  const s = diff < 60000 ? `${Math.floor(diff/1000)}s ago`
    : diff < 3600000    ? `${Math.floor(diff/60000)}m ago`
    : diff < 86400000   ? `${Math.floor(diff/3600000)}h ago`
    : `${Math.floor(diff/86400000)}d ago`;
  return <span style={{ color: C.dimmer, fontSize: 11 }}>{s}</span>;
}

// ── TaskCard ──────────────────────────────────────────────────────────────────

function TaskCard({ task, onCancel }) {
  const meta  = CONNECTOR_META[task.connector] || { icon: '🔧', color: C.accent };
  const color = taskColor(task.status);
  return (
    <div style={{ ...S.card, borderLeft: `3px solid ${color}`, marginBottom: 8, padding: '12px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 18 }}>{meta.icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, color: '#fff', fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{task.title}</div>
          <div style={{ color: C.muted, fontSize: 11 }}>{task.connector} · <TimeAgo ts={task.createdAt} /></div>
        </div>
        <span style={S.badge(color)}>{task.status}</span>
        {task.status !== TaskStatus.DONE && (
          <button style={{ ...S.btn('danger'), padding: '3px 9px', fontSize: 11 }} onClick={() => onCancel(task.id)}>✕</button>
        )}
      </div>

      <ProgressBar pct={task.progress} color={color} />

      {task.steps?.length > 0 && (
        <div style={{ marginTop: 6, color: C.muted, fontSize: 11 }}>
          Step {task.currentStep + 1}/{task.steps.length}: {task.steps[task.currentStep]}
        </div>
      )}

      {task.checkpoint && (
        <div style={{ marginTop: 6, background: '#18181b', borderRadius: 5, padding: '4px 8px', ...S.mono, color: C.accent, fontSize: 10 }}>
          💾 checkpoint saved · resumable
        </div>
      )}

      {task.summary && (
        <div style={{ marginTop: 6, color: C.muted, fontSize: 11, fontStyle: 'italic' }}>{task.summary}</div>
      )}
    </div>
  );
}

// ── ConnectorCard ─────────────────────────────────────────────────────────────

function ConnectorCard({ info, onGrant, onRevoke, onConnect, onDisconnect }) {
  const meta = CONNECTOR_META[info.id] || { icon: '🔧', color: C.accent };
  return (
    <div style={{ ...S.card, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ fontSize: 22, width: 38, height: 38, borderRadius: 9, background: meta.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{meta.icon}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, color: '#fff' }}>{info.name}</div>
          <div style={{ color: C.muted, fontSize: 11 }}>{info.category}</div>
        </div>
        <Dot color={info.connected ? C.success : C.border} />
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {info.capabilities?.slice(0, 4).map(c => <span key={c} style={S.tag}>{c}</span>)}
        {info.capabilities?.length > 4 && <span style={S.tag}>+{info.capabilities.length - 4}</span>}
      </div>

      <div style={{ display: 'flex', gap: 6 }}>
        {info.permitted
          ? <button style={{ ...S.btn('danger'), flex: 1, fontSize: 11 }} onClick={() => onRevoke(info.id)}>Revoke</button>
          : <button style={{ ...S.btn('primary'), flex: 1, fontSize: 11 }} onClick={() => onGrant(info.id)}>Grant Access</button>}
        {info.permitted && (info.connected
          ? <button style={{ ...S.btn(), flex: 1, fontSize: 11 }} onClick={() => onDisconnect(info.id)}>Disconnect</button>
          : <button style={{ ...S.btn('success'), flex: 1, fontSize: 11 }} onClick={() => onConnect(info.id)}>Connect</button>)}
      </div>
    </div>
  );
}

// ── Permission Modal ──────────────────────────────────────────────────────────

function PermissionModal({ connectorId, connectors, onAllow, onDeny }) {
  const info = connectors.find(c => c.id === connectorId);
  const meta = CONNECTOR_META[connectorId] || { icon: '🔧' };
  if (!info) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, background: '#000c', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200 }}>
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: 28, maxWidth: 380, width: '90%' }}>
        <div style={{ fontSize: 28, textAlign: 'center', marginBottom: 8 }}>🔐</div>
        <div style={{ fontWeight: 700, fontSize: 16, textAlign: 'center', color: '#fff', marginBottom: 8 }}>Permission Request</div>
        <p style={{ color: C.muted, lineHeight: 1.6, fontSize: 13, marginBottom: 14 }}>
          Xoltra is requesting access to <strong style={{ color: '#fff' }}>{meta.icon} {info.name}</strong>.
          This allows the agent to read and manipulate data on your behalf.
        </p>
        <div style={{ background: '#18181b', borderRadius: 8, padding: 12, marginBottom: 18 }}>
          {info.capabilities?.map(cap => (
            <div key={cap} style={{ color: C.muted, fontSize: 12, padding: '2px 0' }}>✓ {cap}</div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ ...S.btn(), flex: 1 }} onClick={onDeny}>Deny</button>
          <button style={{ ...S.btn('primary'), flex: 1 }} onClick={onAllow}>Allow</button>
        </div>
      </div>
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

const TABS = [
  { id: 'dashboard',  icon: '⚡', label: 'Dashboard'  },
  { id: 'tasks',      icon: '📋', label: 'Tasks'       },
  { id: 'connectors', icon: '🔗', label: 'Connectors'  },
  { id: 'workflows',  icon: '⚙️', label: 'Workflows'   },
  { id: 'roles',      icon: '📄', label: 'Roles'       },
  { id: 'summaries',  icon: '📊', label: 'Summaries'   },
  { id: 'state',      icon: '💾', label: 'State'       },
];

export default function XoltraDashboard() {
  const [status,      setStatus]      = useState(null);
  const [tab,         setTab]         = useState('dashboard');
  const [taskInput,   setTaskInput]   = useState('');
  const [taskConn,    setTaskConn]    = useState('gmail');
  const [permModal,   setPermModal]   = useState(null);
  const [logs,        setLogs]        = useState(['Xoltra dashboard initialized.']);
  const [apiOk,       setApiOk]       = useState(false);
  const logRef = useRef(null);

  const addLog = useCallback(msg => setLogs(p => [...p.slice(-150), `[${new Date().toLocaleTimeString()}] ${msg}`]), []);

  // Poll status every 1.5s
  useEffect(() => {
    const poll = async () => {
      try {
        const s = await call('GET', '/status');
        setStatus(s);
        setApiOk(true);
      } catch {
        setApiOk(false);
      }
    };
    poll();
    const h = setInterval(poll, 1500);
    return () => clearInterval(h);
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  // ── Actions ────────────────────────────────────────────────────────────────

  const agentAction = async (path) => {
    try {
      await call('POST', `/agent/${path}`);
      addLog(`Agent: ${path}`);
    } catch (e) { addLog(`Error: ${e.message}`); }
  };

  const addTask = async () => {
    if (!taskInput.trim()) return;
    try {
      const t = await call('POST', '/tasks', { title: taskInput, connector: taskConn, instructions: taskInput });
      addLog(`Task added: "${t.title}"`);
      setTaskInput('');
    } catch (e) { addLog(`Error: ${e.message}`); }
  };

  const cancelTask = async (id) => {
    try { await call('DELETE', `/tasks/${id}`); addLog(`Task cancelled: ${id}`); }
    catch (e) { addLog(`Error: ${e.message}`); }
  };

  const grantPermission = async (id) => {
    try { await call('POST', '/permissions/grant', { connectorId: id }); addLog(`Permission granted: ${id}`); }
    catch (e) { addLog(`Error: ${e.message}`); }
  };

  const revokePermission = async (id) => {
    try { await call('POST', '/permissions/revoke', { connectorId: id }); addLog(`Permission revoked: ${id}`); }
    catch (e) { addLog(`Error: ${e.message}`); }
  };

  const runWorkflow = async (id) => {
    try { const r = await call('POST', `/workflows/${id}/run`); addLog(`Workflow ${id} run: ${r.id}`); }
    catch (e) { addLog(`Error: ${e.message}`); }
  };

  const openPermModal = (id) => setPermModal(id);
  const confirmGrant  = () => { if (permModal) { grantPermission(permModal); setPermModal(null); } };

  // ── Derived ────────────────────────────────────────────────────────────────

  const agSt      = status?.status       || AgentStatus.OFFLINE;
  const allTasks  = [...(status?.activeTasks || []), ...(status?.queuedTasks || []), ...(status?.completed || [])];
  const running   = allTasks.filter(t => t.status === TaskStatus.RUNNING);
  const pending   = allTasks.filter(t => t.status === TaskStatus.PENDING);
  const done      = allTasks.filter(t => t.status === TaskStatus.DONE);
  const connInfos = status ? (status.connectors || []) : [];
  const permitted = connInfos.filter(c => c.permitted);
  const color     = agentColor(agSt);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div style={S.root}>
      {/* Permission Modal */}
      {permModal && <PermissionModal connectorId={permModal} connectors={connInfos} onAllow={confirmGrant} onDeny={() => setPermModal(null)} />}

      {/* Topbar */}
      <div style={S.topbar}>
        <span style={S.logo}>Xoltra</span>
        <span style={S.chip(C.accent + '22', C.accent)}>AGENT</span>
        <div style={{ flex: 1 }} />
        {!apiOk && <span style={S.chip(C.danger + '22', C.danger)}>API OFFLINE</span>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, ...S.chip(color + '18', color) }}>
          <Dot color={color} />{agSt}
        </div>
        {(agSt === AgentStatus.IDLE || agSt === AgentStatus.PAUSED || agSt === AgentStatus.OFFLINE) && (
          <button style={S.btn('success')} onClick={() => agentAction('start')}>▶ Start</button>
        )}
        {agSt === AgentStatus.RUNNING && <>
          <button style={S.btn()} onClick={() => agentAction('pause')}>⏸ Pause</button>
          <button style={S.btn('danger')} onClick={() => agentAction('stop')}>⏹ Stop</button>
        </>}
        {agSt === AgentStatus.PAUSED && (
          <button style={S.btn('primary')} onClick={() => agentAction('resume')}>▶ Resume</button>
        )}
        {status?.stateInfo && (
          <span style={{ color: C.dimmer, fontSize: 11 }}>💾 {status.stateInfo.sizeKB} KB</span>
        )}
      </div>

      <div style={S.layout}>
        {/* Sidebar */}
        <div style={S.sidebar}>
          {TABS.map(t => (
            <div key={t.id} style={S.navItem(tab === t.id)} onClick={() => setTab(t.id)}>
              <span>{t.icon}</span>
              <span>{t.label}</span>
              {t.id === 'tasks' && running.length > 0 && (
                <span style={{ marginLeft: 'auto', background: '#3b82f6', color: '#fff', borderRadius: 10, padding: '0 6px', fontSize: 10, fontWeight: 700 }}>{running.length}</span>
              )}
            </div>
          ))}
          <div style={{ flex: 1 }} />
          <div style={{ padding: '8px 10px', fontSize: 10, color: C.dimmer }}>v1.0.0 · Xoltra</div>
        </div>

        {/* Main */}
        <div style={S.main}>

          {/* ── Dashboard ─────────────────────────────────────── */}
          {tab === 'dashboard' && (<>
            <div style={S.grid(4)}>
              {[
                { label: 'Running',     val: running.length,         color: '#3b82f6' },
                { label: 'Pending',     val: pending.length,         color: C.warning },
                { label: 'Completed',   val: done.length + (status?.summaries?.length || 0), color: C.success },
                { label: 'Connections', val: permitted.length,       color: C.accent  },
              ].map(s => (
                <div key={s.label} style={{ ...S.card }}>
                  <div style={{ fontSize: 28, fontWeight: 800, color: s.color }}>{s.val}</div>
                  <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{s.label}</div>
                </div>
              ))}
            </div>

            {running.length > 0 && (
              <div style={S.card}>
                <div style={S.label}>Active Tasks</div>
                {running.map(t => <TaskCard key={t.id} task={t} onCancel={cancelTask} />)}
              </div>
            )}

            <div style={S.card}>
              <div style={S.label}>Quick Add Task</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  style={{ ...S.input, flex: 1 }}
                  placeholder="Describe what you want Xoltra to do..."
                  value={taskInput}
                  onChange={e => setTaskInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addTask()}
                />
                <select
                  style={{ ...S.input, width: 150 }}
                  value={taskConn}
                  onChange={e => setTaskConn(e.target.value)}
                >
                  {connInfos.filter(c => c.permitted).map(c => (
                    <option key={c.id} value={c.id}>{CONNECTOR_META[c.id]?.icon} {c.name}</option>
                  ))}
                </select>
                <button style={S.btn('primary')} onClick={addTask}>Add</button>
              </div>
            </div>

            <div style={S.card}>
              <div style={S.label}>Agent Log</div>
              <div ref={logRef} style={{ background: '#09090b', border: `1px solid ${C.border}`, borderRadius: 8, padding: 12, fontFamily: 'monospace', fontSize: 11, maxHeight: 200, overflow: 'auto' }}>
                {logs.map((l, i) => (
                  <div key={i} style={{ color: l.includes('✅')||l.includes('granted')||l.includes('▶') ? C.success : l.includes('❌')||l.includes('Error') ? C.danger : C.muted, marginBottom: 1 }}>{l}</div>
                ))}
              </div>
            </div>
          </>)}

          {/* ── Tasks ──────────────────────────────────────────── */}
          {tab === 'tasks' && (
            <div style={S.card}>
              <div style={S.label}>All Tasks ({allTasks.length})</div>
              {allTasks.length === 0 && <div style={{ color: C.dimmer, textAlign: 'center', padding: 24 }}>No tasks yet. Add one from the dashboard.</div>}
              {allTasks.map(t => <TaskCard key={t.id} task={t} onCancel={cancelTask} />)}
            </div>
          )}

          {/* ── Connectors ─────────────────────────────────────── */}
          {tab === 'connectors' && (<>
            <div style={S.label}>Connectors ({connInfos.length})</div>
            <div style={S.grid(3)}>
              {connInfos.map(c => (
                <ConnectorCard
                  key={c.id}
                  info={c}
                  onGrant={openPermModal}
                  onRevoke={revokePermission}
                  onConnect={id => addLog(`Connect ${id} — implement OAuth flow`)}
                  onDisconnect={id => addLog(`Disconnected: ${id}`)}
                />
              ))}
            </div>
          </>)}

          {/* ── Workflows ──────────────────────────────────────── */}
          {tab === 'workflows' && (
            <div style={S.card}>
              <div style={S.label}>Workflow Templates</div>
              <div style={{ color: C.muted, fontSize: 12, marginBottom: 14 }}>Pre-built multi-connector automations. Active via workflow_builder.role.</div>
              {(status?.workflows || []).map(wf => (
                <div key={wf.id} style={{ ...S.card, background: '#18181b', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, color: '#fff' }}>{wf.name}</div>
                    <div style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{wf.description}</div>
                    <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
                      {wf.nodes?.map(n => <span key={n.id} style={{ ...S.tag, fontSize: 10 }}>{CONNECTOR_META[n.connector]?.icon} {n.action}</span>)}
                    </div>
                  </div>
                  <button style={S.btn('primary')} onClick={() => runWorkflow(wf.id)}>▶ Run</button>
                </div>
              ))}
            </div>
          )}

          {/* ── Roles ──────────────────────────────────────────── */}
          {tab === 'roles' && (
            <div style={S.card}>
              <div style={S.label}>Role Files · Auto-Watched</div>
              <div style={{ color: C.muted, fontSize: 12, marginBottom: 14 }}>
                Drop any <code style={{ background: '#18181b', padding: '1px 5px', borderRadius: 4 }}>.role</code> file into <code style={{ background: '#18181b', padding: '1px 5px', borderRadius: 4 }}>.xoltra/roles/</code> — changes apply instantly. <br />
                <strong style={{ color: C.accent }}>workflow_builder.role</strong> is pre-seeded and always active.
              </div>
              {(status?.roles || []).map(r => (
                <div key={r.id} style={{ ...S.card, background: '#18181b', borderLeft: `3px solid ${r.active ? C.accent : C.border}`, marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ ...S.mono, color: C.accent }}>📄 {r.name}</span>
                    <span style={S.badge(r.active ? C.success : C.muted)}>{r.active ? 'ACTIVE' : 'INACTIVE'}</span>
                    <TimeAgo ts={r.lastModified} />
                  </div>
                  <div style={{ color: C.muted, fontSize: 11, marginTop: 6 }}>{r.description}</div>
                  <div style={{ display: 'flex', gap: 4, marginTop: 8 }}>
                    {r.permissions?.map(p => <span key={p} style={{ ...S.tag, color: C.accent, fontSize: 10 }}>{p}</span>)}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* ── Summaries ──────────────────────────────────────── */}
          {tab === 'summaries' && (
            <div style={S.card}>
              <div style={S.label}>Task Summaries</div>
              {(status?.summaries || []).length === 0 && <div style={{ color: C.dimmer, textAlign: 'center', padding: 24 }}>No completed tasks yet.</div>}
              {(status?.summaries || []).map(s => {
                const meta = CONNECTOR_META[s.connector] || { icon: '🔧' };
                return (
                  <div key={s.id} style={{ ...S.card, background: '#18181b', marginBottom: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <span>{meta.icon}</span>
                      <strong style={{ color: '#fff', fontSize: 13 }}>{s.taskTitle}</strong>
                      <span style={S.badge(C.success)}>DONE</span>
                      <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                        <TimeAgo ts={s.completedAt} />
                        <span style={{ color: C.dimmer, fontSize: 11 }}>· {s.duration}</span>
                      </div>
                    </div>
                    <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.6 }}>{s.summary}</div>
                  </div>
                );
              })}
            </div>
          )}

          {/* ── State ──────────────────────────────────────────── */}
          {tab === 'state' && (
            <div style={S.card}>
              <div style={S.label}>Persistent State · .xoltra/</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                {[
                  ['State Version',        status?.stateInfo?.version  || '—'],
                  ['Size',                 status?.stateInfo?.sizeKB   ? `${status.stateInfo.sizeKB} KB` : '—'],
                  ['Last Saved',           status?.stateInfo?.savedAt  || null],
                  ['Queued Tasks',         pending.length],
                  ['Active Tasks',         running.length],
                  ['Completed (cached)',   done.length],
                ].map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '9px 0', borderBottom: `1px solid #18181b` }}>
                    <span style={{ color: C.muted }}>{k}</span>
                    <span style={{ color: '#fff', fontWeight: 600 }}>
                      {typeof v === 'number' && k === 'Last Saved' ? <TimeAgo ts={v} /> : String(v ?? '—')}
                    </span>
                  </div>
                ))}
              </div>

              <div style={{ marginTop: 14, background: '#09090b', borderRadius: 8, padding: 14, ...S.mono, color: C.accent, lineHeight: 1.8 }}>
                .xoltra/<br />
                ├── agent_state.bin&nbsp;&nbsp;&nbsp;← compressed state<br />
                ├── meta.json&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;← version + size<br />
                ├── checkpoints/<br />
                │&nbsp;&nbsp;&nbsp;└── *.ckpt&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;← per-task resume data<br />
                └── roles/<br />
                &nbsp;&nbsp;&nbsp;&nbsp;└── workflow_builder.role
              </div>

              <div style={{ marginTop: 14, color: C.muted, fontSize: 12, lineHeight: 1.7 }}>
                When connectivity drops, the agent pauses and writes all checkpoints to disk.
                On reconnect, <strong style={{ color: '#fff' }}>agent.start()</strong> calls <em>_loadAndResume()</em>
                and re-queues every paused task from its saved step — no work is lost.
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
