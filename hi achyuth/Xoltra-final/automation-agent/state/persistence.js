/**
 * Xoltra State Manager
 * Compressed, KB-sized persistence for agent resume after disconnect
 */

'use strict';
const fs   = require('fs').promises;
const path = require('path');
const zlib = require('zlib');
const { promisify } = require('util');

const gzip   = promisify(zlib.gzip);
const gunzip = promisify(zlib.gunzip);

const MAX_KB = 512; // hard cap per save

class StateManager {
  constructor(stateDir) {
    this.stateDir      = stateDir;
    this.statePath     = path.join(stateDir, 'agent_state.bin');
    this.checkpointDir = path.join(stateDir, 'checkpoints');
    this.metaPath      = path.join(stateDir, 'meta.json');
    this._meta         = { version: 0, savedAt: null, sizeKB: 0, dir: stateDir };
  }

  async init() {
    await fs.mkdir(this.stateDir,      { recursive: true });
    await fs.mkdir(this.checkpointDir, { recursive: true });
    // Write default role files on first init
    await this._seedRoles();
  }

  async save(state) {
    let payload = JSON.stringify(state);

    // Trim if over limit
    if (Buffer.byteLength(payload) / 1024 > MAX_KB) {
      state.completedTasks = (state.completedTasks || []).slice(-10);
      state.summaries      = (state.summaries      || []).slice(-10);
      payload              = JSON.stringify(state);
    }

    const compressed = await gzip(Buffer.from(payload));
    await fs.writeFile(this.statePath, compressed);

    this._meta = {
      version : this._meta.version + 1,
      savedAt : Date.now(),
      sizeKB  : (compressed.length / 1024).toFixed(2),
      dir     : this.stateDir,
    };
    await fs.writeFile(this.metaPath, JSON.stringify(this._meta, null, 2));
  }

  async load() {
    try {
      const buf  = await fs.readFile(this.statePath);
      const json = await gunzip(buf);
      return JSON.parse(json.toString('utf8'));
    } catch {
      return null;
    }
  }

  async saveCheckpoint(taskId, data) {
    const file = path.join(this.checkpointDir, `${taskId}.ckpt`);
    const json = JSON.stringify({ taskId, data, savedAt: Date.now() });
    await fs.writeFile(file, json);
  }

  async loadCheckpoint(taskId) {
    try {
      const file = path.join(this.checkpointDir, `${taskId}.ckpt`);
      return JSON.parse(await fs.readFile(file, 'utf8'));
    } catch {
      return null;
    }
  }

  async clearCheckpoint(taskId) {
    try { await fs.unlink(path.join(this.checkpointDir, `${taskId}.ckpt`)); } catch {}
  }

  async listCheckpoints() {
    try {
      const files = await fs.readdir(this.checkpointDir);
      return files.filter(f => f.endsWith('.ckpt')).map(f => f.replace('.ckpt', ''));
    } catch {
      return [];
    }
  }

  getInfo() { return { ...this._meta }; }

  // Seed default role files if not present
  async _seedRoles() {
    const rolesDir = path.join(this.stateDir, 'roles');
    await fs.mkdir(rolesDir, { recursive: true });

    const wfRole = path.join(rolesDir, 'workflow_builder.role');
    try {
      await fs.access(wfRole);
    } catch {
      await fs.writeFile(wfRole, JSON.stringify({
        active      : true,
        description : 'Pre-made role — extends Xoltra to hundreds of services via Workflow Builder',
        permissions : ['run_workflow', 'build_workflow', 'trigger_automation', 'connect_services'],
        connectors  : ['workflow'],
        capabilities: ['*'],
      }, null, 2));
    }
  }
}

module.exports = { StateManager };
