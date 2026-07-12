/**
 * Xoltra Workflow Builder
 * Templated multi-connector automations — extends agent to hundreds of services.
 * Active when workflow_builder.role file is present.
 */

'use strict';

const TEMPLATES = {
  email_to_doc: {
    name       : 'Email → Word Doc',
    description: 'Summarize unread emails and write to a Word document',
    nodes      : [
      { id: 'n0', connector: 'gmail',    action: 'fetch',    params: { query: 'is:unread' }, next: ['n1'] },
      { id: 'n1', connector: 'gmail',    action: 'classify',                                 next: ['n2'] },
      { id: 'n2', connector: 'word',     action: 'write_doc', params: { template: 'email_summary' }, next: [] },
    ],
  },
  web_to_sheet: {
    name       : 'Web Scrape → Sheets',
    description: 'Extract data from a URL and populate a spreadsheet',
    nodes      : [
      { id: 'n0', connector: 'browser',  action: 'navigate',     next: ['n1'] },
      { id: 'n1', connector: 'browser',  action: 'extract',      next: ['n2'] },
      { id: 'n2', connector: 'workflow', action: 'run_workflow', params: { target: 'sheets' }, next: [] },
    ],
  },
  code_review: {
    name       : 'AI Code Review (Codex)',
    description: 'Delegate code review to Codex agent and return a report',
    nodes      : [
      { id: 'n0', connector: 'codex',    action: 'handshake', next: ['n1'] },
      { id: 'n1', connector: 'codex',    action: 'delegate',  params: { task: 'review_code' }, next: ['n2'] },
      { id: 'n2', connector: 'codex',    action: 'collect',   next: [] },
    ],
  },
  antigravity_deploy: {
    name       : 'Deploy via Antigravity',
    description: 'Spawn an Antigravity agent to build and deploy your project',
    nodes      : [
      { id: 'n0', connector: 'antigravity', action: 'handshake', next: ['n1'] },
      { id: 'n1', connector: 'antigravity', action: 'spawn',     params: { task: 'deploy' }, next: ['n2'] },
      { id: 'n2', connector: 'antigravity', action: 'execute',   next: ['n3'] },
      { id: 'n3', connector: 'antigravity', action: 'sync',      next: [] },
    ],
  },
  inbox_zero: {
    name       : 'Inbox Zero',
    description: 'Read, classify, archive, and summarise all Gmail in one pass',
    nodes      : [
      { id: 'n0', connector: 'gmail',    action: 'fetch',     params: { query: 'in:inbox' }, next: ['n1'] },
      { id: 'n1', connector: 'gmail',    action: 'classify',  next: ['n2'] },
      { id: 'n2', connector: 'gmail',    action: 'apply',     next: ['n3'] },
      { id: 'n3', connector: 'gmail',    action: 'summarize', next: [] },
    ],
  },
};

// ── Node & Workflow classes ────────────────────────────────────────────────────

class WorkflowNode {
  constructor({ id, connector, action, params = {}, next = [] }) {
    this.id        = id || `node_${Date.now()}`;
    this.connector = connector;
    this.action    = action;
    this.params    = params;
    this.next      = next;
    this.status    = 'pending';
    this.result    = null;
    this.error     = null;
  }
  toJSON() { return { id: this.id, connector: this.connector, action: this.action, params: this.params, next: this.next, status: this.status }; }
}

class Workflow {
  constructor({ id, name, description, nodes = [], triggers = [] }) {
    this.id          = id || `wf_${Date.now()}`;
    this.name        = name;
    this.description = description;
    this.nodes       = nodes.map(n => new WorkflowNode(n));
    this.triggers    = triggers;
    this.status      = 'idle';
    this.createdAt   = Date.now();
    this.lastRunAt   = null;
    this.runHistory  = [];
  }

  toJSON() {
    return {
      id: this.id, name: this.name, description: this.description,
      nodes: this.nodes.map(n => n.toJSON()), triggers: this.triggers,
      status: this.status, createdAt: this.createdAt, lastRunAt: this.lastRunAt,
      runs: this.runHistory.length,
    };
  }
}

// ── WorkflowBuilder ───────────────────────────────────────────────────────────

class WorkflowBuilder {
  constructor(connectorRegistry) {
    this.connectors = connectorRegistry;
    this._workflows = new Map();
    this._loadTemplates();
  }

  _loadTemplates() {
    for (const [id, tpl] of Object.entries(TEMPLATES)) {
      const wf = new Workflow({ id, ...tpl });
      this._workflows.set(id, wf);
    }
  }

  create(definition) {
    const wf = new Workflow(definition);
    this._workflows.set(wf.id, wf);
    return wf;
  }

  get(id)    { return this._workflows.get(id); }
  list()     { return [...this._workflows.values()].map(w => w.toJSON()); }
  delete(id) { return this._workflows.delete(id); }

  /**
   * Run a workflow by id.
   * @param {string} workflowId
   * @param {object} params   — merged into each node's params
   * @param {function} onProgress — (workflow, node) => void
   */
  async run(workflowId, params = {}, onProgress) {
    const wf = this._workflows.get(workflowId);
    if (!wf) throw new Error(`Workflow not found: ${workflowId}`);

    wf.status    = 'running';
    wf.lastRunAt = Date.now();
    const run    = { id: `run_${Date.now()}`, workflowId, startedAt: Date.now(), steps: [] };

    for (const node of wf.nodes) {
      node.status = 'running';
      onProgress?.(wf.toJSON(), node.toJSON());

      const connector = this.connectors.get(node.connector);
      if (!connector) {
        node.status = 'skipped';
        run.steps.push({ nodeId: node.id, skipped: true, reason: `No permission: ${node.connector}` });
        continue;
      }

      try {
        // Minimal task stub so connector.executeStep works
        const stub = {
          id: run.id, checkpoint: null,
          saveCheckpoint(data) { this.checkpoint = data; },
        };
        const result = await connector.executeStep(
          { action: node.action, params: { ...node.params, ...params } },
          stub
        );
        node.status = 'done';
        node.result = result;
        run.steps.push({ nodeId: node.id, ok: result.ok });
      } catch (err) {
        node.status = 'failed';
        node.error  = err.message;
        wf.status   = 'failed';
        run.steps.push({ nodeId: node.id, error: err.message });
        wf.runHistory.push({ ...run, completedAt: Date.now(), status: 'failed' });
        throw err;
      }
    }

    wf.status = 'idle';
    wf.runHistory.push({ ...run, completedAt: Date.now(), status: 'done' });
    return run;
  }
}

module.exports = { WorkflowBuilder, Workflow, WorkflowNode, TEMPLATES };
