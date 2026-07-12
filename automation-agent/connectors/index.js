/**
 * Xoltra Connector Registry
 * Gmail · Word · Web · Codex · Antigravity · WorkflowBuilder
 */

'use strict';

// ── Base ──────────────────────────────────────────────────────────────────────

class BaseConnector {
  constructor(id, name, category, capabilities) {
    this.id           = id;
    this.name         = name;
    this.category     = category;
    this.capabilities = capabilities;
    this.connected    = false;
    this.credentials  = null;
  }
  async connect(creds)          { this.credentials = creds; this.connected = true; return this; }
  async disconnect()            { this.connected = false; return this; }
  async planSteps(instructions) { throw new Error('planSteps not implemented'); }
  async executeStep(step, task) { throw new Error('executeStep not implemented'); }
}

// ── Gmail ─────────────────────────────────────────────────────────────────────

class GmailConnector extends BaseConnector {
  constructor() {
    super('gmail', 'Gmail', 'Communication',
      ['read_email', 'send_email', 'search_email', 'label_email', 'delete_email', 'create_draft', 'unsubscribe']);
    this.gmail = null;
  }

  async connect({ clientId, clientSecret, redirectUri, refreshToken }) {
    const { google } = require('googleapis');
    const auth = new google.auth.OAuth2(clientId, clientSecret, redirectUri);
    auth.setCredentials({ refresh_token: refreshToken });
    this.gmail     = google.gmail({ version: 'v1', auth });
    this.connected = true;
    return this;
  }

  async planSteps(instructions) {
    return [
      { label: 'Authenticate with Gmail API',       action: 'auth'       },
      { label: 'Fetch matching emails',             action: 'fetch',     params: { query: instructions } },
      { label: 'AI classify by priority/topic',     action: 'classify'   },
      { label: 'Apply labels & archive',            action: 'apply'      },
      { label: 'Generate inbox summary',            action: 'summarize'  },
    ];
  }

  async executeStep(step, task) {
    switch (step.action) {
      case 'auth': {
        await this.gmail.users.getProfile({ userId: 'me' });
        return { ok: true };
      }
      case 'fetch': {
        const res  = await this.gmail.users.messages.list({ userId: 'me', q: step.params?.query || 'is:unread', maxResults: 200 });
        const msgs = res.data.messages || [];
        task.saveCheckpoint({ messages: msgs.map(m => m.id), processed: 0 });
        return { ok: true, data: msgs, checkpoint: task.checkpoint };
      }
      case 'classify': {
        // Batch-fetch and classify
        const ids       = task.checkpoint?.messages || [];
        const classified = { priority: [], archive: [], spam: [] };
        // In real impl: call AI for classification; here we simulate
        task.saveCheckpoint({ ...task.checkpoint, classified });
        return { ok: true, data: classified, checkpoint: task.checkpoint };
      }
      case 'apply': {
        const { classified } = task.checkpoint || {};
        if (!classified) return { ok: true };
        // Apply Gmail labels via batch modify
        const batch = Object.entries(classified).flatMap(([label, ids]) =>
          ids.map(id => this.gmail.users.messages.modify({ userId: 'me', id, requestBody: { addLabelIds: [label.toUpperCase()] } }))
        );
        await Promise.allSettled(batch);
        return { ok: true };
      }
      case 'summarize': return { ok: true, summary: 'Inbox processed' };
      default:          return { ok: true };
    }
  }

  async sendEmail({ to, subject, body }) {
    const raw = Buffer.from([`To: ${to}`, `Subject: ${subject}`, '', body].join('\r\n')).toString('base64url');
    return this.gmail.users.messages.send({ userId: 'me', requestBody: { raw } });
  }

  async searchEmails(query, max = 50) {
    const res = await this.gmail.users.messages.list({ userId: 'me', q: query, maxResults: max });
    return res.data.messages || [];
  }
}

// ── Microsoft Word ────────────────────────────────────────────────────────────

class WordConnector extends BaseConnector {
  constructor() {
    super('word', 'Microsoft Word', 'Office',
      ['read_doc', 'write_doc', 'edit_doc', 'format_doc', 'export_pdf', 'track_changes', 'insert_table']);
  }

  async connect({ accessToken }) {
    this.token     = accessToken;
    this.baseUrl   = 'https://graph.microsoft.com/v1.0';
    this.connected = true;
    return this;
  }

  _headers() {
    return { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' };
  }

  async planSteps(instructions) {
    return [
      { label: 'Authenticate with Microsoft Graph', action: 'auth'    },
      { label: 'Open/locate document',              action: 'open'    },
      { label: 'Read current content',              action: 'read'    },
      { label: 'Apply AI-driven edits',             action: 'edit',   params: { instructions } },
      { label: 'Format & style document',           action: 'format'  },
      { label: 'Save & export',                     action: 'save'    },
    ];
  }

  async executeStep(step, task) {
    const h = this._headers();
    switch (step.action) {
      case 'auth': {
        const res = await fetch(`${this.baseUrl}/me`, { headers: h });
        return { ok: res.ok };
      }
      case 'open': {
        const res   = await fetch(`${this.baseUrl}/me/drive/root/children`, { headers: h });
        const data  = await res.json();
        const files = (data.value || []).filter(f => f.name?.endsWith('.docx'));
        task.saveCheckpoint({ files: files.map(f => ({ id: f.id, name: f.name })), currentFileId: files[0]?.id });
        return { ok: true, data: files, checkpoint: task.checkpoint };
      }
      case 'read': {
        const { currentFileId } = task.checkpoint || {};
        if (!currentFileId) return { ok: true };
        const res  = await fetch(`${this.baseUrl}/me/drive/items/${currentFileId}/content`, { headers: h });
        const text = await res.text();
        task.saveCheckpoint({ ...task.checkpoint, content: text.slice(0, 10000) });
        return { ok: true, checkpoint: task.checkpoint };
      }
      case 'edit': {
        // In real impl: use docx editing library or Word JS API
        return { ok: true };
      }
      case 'format': return { ok: true };
      case 'save':   return { ok: true };
      default:       return { ok: true };
    }
  }
}

// ── Web Browser ───────────────────────────────────────────────────────────────

class WebConnector extends BaseConnector {
  constructor() {
    super('browser', 'Web Browser', 'Web',
      ['navigate', 'read_page', 'fill_form', 'click', 'screenshot', 'extract_data', 'wait_element', 'scroll', 'download']);
    this.browser = null;
    this.page    = null;
  }

  async connect({ headless = true } = {}) {
    const puppeteer  = require('puppeteer');
    this.browser     = await puppeteer.launch({ headless });
    this.page        = await this.browser.newPage();
    await this.page.setUserAgent('Mozilla/5.0 (compatible; Xoltra/1.0)');
    this.connected   = true;
    return this;
  }

  async disconnect() {
    if (this.browser) await this.browser.close();
    this.connected = false;
    return this;
  }

  async planSteps(instructions) {
    return [
      { label: 'Launch browser context',   action: 'launch'   },
      { label: 'Navigate to target URL',   action: 'navigate' },
      { label: 'Wait for page load',       action: 'wait'     },
      { label: 'Extract structured data',  action: 'extract'  },
      { label: 'Post-process & structure', action: 'process'  },
    ];
  }

  async executeStep(step, task) {
    switch (step.action) {
      case 'launch':   return { ok: true };
      case 'navigate': {
        const url = step.params?.url || task.instructions;
        await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
        task.saveCheckpoint({ url, navigatedAt: Date.now() });
        return { ok: true, checkpoint: task.checkpoint };
      }
      case 'wait': {
        if (step.params?.selector) await this.page.waitForSelector(step.params.selector, { timeout: 10000 }).catch(() => {});
        return { ok: true };
      }
      case 'extract': {
        const text  = await this.page.evaluate(() => document.body.innerText);
        const title = await this.page.title();
        const links = await this.page.evaluate(() =>
          [...document.querySelectorAll('a[href]')].slice(0, 50).map(a => ({ text: a.innerText.trim(), href: a.href }))
        );
        task.saveCheckpoint({ ...task.checkpoint, data: { title, text: text.slice(0, 5000), links } });
        return { ok: true, data: task.checkpoint.data, checkpoint: task.checkpoint };
      }
      case 'fill_form': {
        for (const [sel, val] of Object.entries(step.params?.fields || {})) {
          await this.page.type(sel, String(val), { delay: 30 });
        }
        return { ok: true };
      }
      case 'click': {
        await this.page.click(step.params?.selector);
        return { ok: true };
      }
      case 'screenshot': {
        const buf = await this.page.screenshot({ fullPage: true });
        return { ok: true, data: buf.toString('base64') };
      }
      case 'process': return { ok: true };
      default:        return { ok: true };
    }
  }
}

// ── Codex IDE ─────────────────────────────────────────────────────────────────

class CodexConnector extends BaseConnector {
  constructor() {
    super('codex', 'Codex IDE', 'IDE',
      ['run_agent', 'use_tools', 'read_code', 'write_code', 'exec_cmd', 'run_tests', 'lint', 'git_op']);
    this.apiUrl = null;
    this.apiKey = null;
  }

  async connect({ apiUrl = 'http://localhost:3001', apiKey } = {}) {
    this.apiUrl    = apiUrl;
    this.apiKey    = apiKey;
    this.connected = true;
    return this;
  }

  _headers() {
    return { 'Content-Type': 'application/json', ...(this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {}) };
  }

  async planSteps(instructions) {
    return [
      { label: 'Handshake with Codex agent',     action: 'handshake' },
      { label: 'Delegate task to Codex agent',   action: 'delegate',  params: { instructions } },
      { label: 'Stream execution progress',       action: 'monitor'   },
      { label: 'Collect & validate results',      action: 'collect'   },
    ];
  }

  async executeStep(step, task) {
    const h = this._headers();
    switch (step.action) {
      case 'handshake': {
        const res = await fetch(`${this.apiUrl}/health`, { headers: h });
        return { ok: res.ok };
      }
      case 'delegate': {
        const res  = await fetch(`${this.apiUrl}/agent/run`, {
          method: 'POST', headers: h,
          body: JSON.stringify({ task: step.params?.instructions, tools: ['read_file', 'write_file', 'exec', 'search', 'lint', 'test'] }),
        });
        const data = await res.json();
        task.saveCheckpoint({ jobId: data.jobId });
        return { ok: true, data, checkpoint: { jobId: data.jobId } };
      }
      case 'monitor': {
        const { jobId } = task.checkpoint || {};
        if (!jobId) return { ok: true };
        // Poll until done
        for (let i = 0; i < 60; i++) {
          const res  = await fetch(`${this.apiUrl}/agent/status/${jobId}`, { headers: h });
          const data = await res.json();
          if (data.status === 'done' || data.status === 'failed') return { ok: true, data };
          await new Promise(r => setTimeout(r, 2000));
        }
        return { ok: true };
      }
      case 'collect': {
        const { jobId } = task.checkpoint || {};
        if (!jobId) return { ok: true };
        const res = await fetch(`${this.apiUrl}/agent/result/${jobId}`, { headers: h });
        return { ok: true, data: await res.json() };
      }
      default: return { ok: true };
    }
  }
}

// ── Antigravity IDE ───────────────────────────────────────────────────────────

class AntigravityConnector extends BaseConnector {
  constructor() {
    super('antigravity', 'Antigravity IDE', 'IDE',
      ['run_agent', 'use_tools', 'manage_project', 'debug', 'deploy', 'run_pipeline', 'spawn_agent']);
    this.apiUrl = null;
    this.apiKey = null;
  }

  async connect({ apiUrl = 'http://localhost:3002', apiKey } = {}) {
    this.apiUrl    = apiUrl;
    this.apiKey    = apiKey;
    this.connected = true;
    return this;
  }

  _headers() {
    return { 'Content-Type': 'application/json', ...(this.apiKey ? { 'X-Api-Key': this.apiKey } : {}) };
  }

  async planSteps(instructions) {
    return [
      { label: 'Handshake with Antigravity',    action: 'handshake'    },
      { label: 'Spawn delegate agent',          action: 'spawn',       params: { instructions } },
      { label: 'Execute via AG tools',          action: 'execute'      },
      { label: 'Sync results to Xoltra',        action: 'sync'         },
    ];
  }

  async executeStep(step, task) {
    const h = this._headers();
    switch (step.action) {
      case 'handshake': {
        const res = await fetch(`${this.apiUrl}/api/v1/ping`, { headers: h });
        return { ok: res.ok };
      }
      case 'spawn': {
        const res  = await fetch(`${this.apiUrl}/api/v1/agents/spawn`, {
          method: 'POST', headers: h,
          body: JSON.stringify({ role: 'xoltra_delegate', instructions: step.params?.instructions, tools: '*' }),
        });
        const data = await res.json();
        task.saveCheckpoint({ agentId: data.agentId, sessionToken: data.sessionToken });
        return { ok: true, data, checkpoint: task.checkpoint };
      }
      case 'execute': {
        const { agentId, sessionToken } = task.checkpoint || {};
        const res = await fetch(`${this.apiUrl}/api/v1/agents/${agentId}/run`, {
          method: 'POST', headers: { ...h, 'X-Session': sessionToken },
        });
        return { ok: true, data: await res.json() };
      }
      case 'sync': {
        const { agentId } = task.checkpoint || {};
        const res = await fetch(`${this.apiUrl}/api/v1/agents/${agentId}/results`, { headers: h });
        return { ok: true, data: await res.json() };
      }
      default: return { ok: true };
    }
  }
}

// ── Workflow Builder ──────────────────────────────────────────────────────────

class WorkflowBuilderConnector extends BaseConnector {
  constructor() {
    super('workflow', 'Workflow Builder', 'Automation',
      ['run_workflow', 'build_workflow', 'trigger_automation', 'connect_services', 'schedule', 'webhook']);
    // Pre-made role: always active when workflow_builder.role file is present
    this.role      = 'workflow_builder';
    this.connected = true; // self-contained
  }

  async connect() { this.connected = true; return this; }

  async planSteps(instructions) {
    return [
      { label: 'Parse workflow definition',  action: 'parse'    },
      { label: 'Build execution graph',      action: 'build'    },
      { label: 'Validate all connections',   action: 'validate' },
      { label: 'Execute workflow nodes',     action: 'execute'  },
      { label: 'Emit completion report',     action: 'report'   },
    ];
  }

  async executeStep(step, task) {
    switch (step.action) {
      case 'parse':    return { ok: true };
      case 'build': {
        const wfId = `wf_${Date.now()}`;
        task.saveCheckpoint({ workflowId: wfId });
        return { ok: true, checkpoint: { workflowId: wfId } };
      }
      case 'validate': return { ok: true };
      case 'execute':  return { ok: true };
      case 'report':   return { ok: true };
      default:         return { ok: true };
    }
  }
}

// ── Registry ──────────────────────────────────────────────────────────────────

class ConnectorRegistry {
  constructor(permissions = {}) {
    this.permissions = permissions;
    this._map = {
      gmail       : new GmailConnector(),
      word        : new WordConnector(),
      browser     : new WebConnector(),
      codex       : new CodexConnector(),
      antigravity : new AntigravityConnector(),
      workflow    : new WorkflowBuilderConnector(),
    };
  }

  get(id) {
    return this.permissions[id] ? (this._map[id] || null) : null;
  }

  all()                       { return Object.values(this._map); }
  updatePermissions(p)        { this.permissions = p; }

  async connect(id, creds)    {
    const c = this._map[id];
    if (!c) throw new Error(`Unknown connector: ${id}`);
    await c.connect(creds);
    return c;
  }

  async disconnect(id)        {
    const c = this._map[id];
    if (c) await c.disconnect();
  }

  info() {
    return Object.entries(this._map).map(([id, c]) => ({
      id, name: c.name, category: c.category,
      capabilities: c.capabilities,
      connected: c.connected,
      permitted: !!this.permissions[id],
    }));
  }
}

module.exports = {
  ConnectorRegistry,
  GmailConnector,
  WordConnector,
  WebConnector,
  CodexConnector,
  AntigravityConnector,
  WorkflowBuilderConnector,
};
