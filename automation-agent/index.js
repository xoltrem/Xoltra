/**
 * Xoltra — Main Entry Point
 * Starts agent + REST API on :4000. Auto-resumes from .xoltra/ on restart.
 */

'use strict';
const http = require('http');
const { XoltraAgent } = require('./core/agent_core');

const PORT      = process.env.PORT       || 4000;
const STATE_DIR = process.env.XOLTRA_DIR || '.xoltra';

// ── Agent ─────────────────────────────────────────────────────────────────────

const agent = new XoltraAgent({
  stateDir    : STATE_DIR,
  maxConcurrent: 3,
  permissions : {
    gmail       : false,
    word        : false,
    browser     : false,
    codex       : false,
    antigravity : false,
    workflow    : true,   // Workflow Builder always on (role file present)
  },
});

agent.on('log',            msg            => console.log(`[XOLTRA] ${msg}`));
agent.on('status',         s              => console.log(`[XOLTRA] Status → ${s}`));
agent.on('task:done',      t              => console.log(`[XOLTRA] ✅ ${t.title}`));
agent.on('task:error',     ({ task, error}) => console.error(`[XOLTRA] ❌ ${task.title}: ${error}`));
agent.on('role:changed',   ({ role, type }) => console.log(`[XOLTRA] Role ${type}: ${role.name}`));

// ── Helpers ───────────────────────────────────────────────────────────────────

function json(res, code, body) {
  res.writeHead(code, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
  res.end(JSON.stringify(body));
}

async function readBody(req) {
  return new Promise(resolve => {
    let buf = '';
    req.on('data', c => buf += c);
    req.on('end',  () => { try { resolve(JSON.parse(buf || '{}')); } catch { resolve({}); } });
  });
}

// ── Router ────────────────────────────────────────────────────────────────────

const routes = {
  'GET /status'          : async ()      => agent.getStatus(),
  'POST /agent/start'    : async ()      => { await agent.start();  return { ok: true }; },
  'POST /agent/pause'    : async ()      => { await agent.pause();  return { ok: true }; },
  'POST /agent/resume'   : async ()      => { await agent.resume(); return { ok: true }; },
  'POST /agent/stop'     : async ()      => { await agent.stop();   return { ok: true }; },

  'POST /tasks'          : async (b)     => (await agent.addTask(b)).toJSON(),
  'DELETE /tasks/:id'    : async (_, id) => { await agent.cancelTask(id); return { ok: true }; },

  'POST /permissions/grant'  : async (b) => { agent.grantPermission(b.connectorId);  return { ok: true }; },
  'POST /permissions/revoke' : async (b) => { agent.revokePermission(b.connectorId); return { ok: true }; },

  'GET /workflows'           : async ()      => agent.workflows.list(),
  'POST /workflows'          : async (b)     => agent.workflows.create(b).toJSON(),
  'POST /workflows/:id/run'  : async (b, id) => agent.workflows.run(id, b),

  'GET /roles'               : async ()  => agent.roles.getAll(),
  'GET /connectors'          : async ()  => agent.connectors.info(),
};

// ── Server ────────────────────────────────────────────────────────────────────

const server = http.createServer(async (req, res) => {
  // CORS preflight
  res.setHeader('Access-Control-Allow-Origin',  '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,DELETE,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const url     = req.url.split('?')[0].replace(/\/$/, '') || '/';
  const method  = req.method;
  const body    = await readBody(req);

  // Match dynamic segments (:id)
  let handler = null;
  let paramId = null;
  for (const [pattern, fn] of Object.entries(routes)) {
    const [pm, pp] = pattern.split(' ');
    if (pm !== method) continue;
    if (pp === url) { handler = fn; break; }
    // e.g. /tasks/:id
    const re = new RegExp('^' + pp.replace(/:[\w]+/g, '([^/]+)') + '$');
    const m  = url.match(re);
    if (m) { handler = fn; paramId = m[1]; break; }
  }

  if (!handler) { json(res, 404, { error: 'Not found' }); return; }

  try {
    const result = await handler(body, paramId);
    json(res, 200, result);
  } catch (err) {
    console.error('[XOLTRA] API error:', err.message);
    json(res, 500, { error: err.message });
  }
});

// ── Boot ──────────────────────────────────────────────────────────────────────

server.listen(PORT, async () => {
  console.log(`[XOLTRA] API  → http://localhost:${PORT}`);
  console.log(`[XOLTRA] State→ ${STATE_DIR}/`);
  try { await agent.start(); }
  catch (err) { console.error('[XOLTRA] Boot error:', err.message); }
});

// ── Graceful shutdown ─────────────────────────────────────────────────────────

const shutdown = async (sig) => {
  console.log(`\n[XOLTRA] ${sig} — pausing agent and saving state...`);
  await agent.pause(); // pause (not stop) — preserves full queue + checkpoints
  server.close(() => process.exit(0));
};

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT',  () => shutdown('SIGINT'));

module.exports = { agent, server };
