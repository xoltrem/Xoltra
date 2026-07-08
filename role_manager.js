/**
 * Xoltra Role Manager
 * Watches .role files recursively. Any change is instantly applied.
 * workflow_builder.role → pre-made role always active when file exists.
 */

'use strict';
const fs   = require('fs');
const path = require('path');

const EXT = '.role';

class Role {
  constructor(filePath, raw) {
    this.id           = path.basename(filePath, EXT);
    this.name         = path.basename(filePath);
    this.filePath     = filePath;
    this.active       = raw.active !== false;
    this.description  = raw.description  || '';
    this.permissions  = Array.isArray(raw.permissions)  ? raw.permissions  : [];
    this.capabilities = Array.isArray(raw.capabilities) ? raw.capabilities : [];
    this.connectors   = Array.isArray(raw.connectors)   ? raw.connectors   : [];
    this.workflows    = Array.isArray(raw.workflows)    ? raw.workflows    : [];
    this.loadedAt     = Date.now();
    try { this.lastModified = fs.statSync(filePath).mtimeMs; } catch { this.lastModified = this.loadedAt; }
  }

  static parse(filePath, content) {
    try {
      return new Role(filePath, JSON.parse(content));
    } catch {
      // Fallback: simple key: value lines
      const raw = {};
      for (const line of content.split('\n')) {
        const sep = line.indexOf(':');
        if (sep < 1) continue;
        const k = line.slice(0, sep).trim();
        const v = line.slice(sep + 1).trim();
        try { raw[k] = JSON.parse(v); } catch { raw[k] = v; }
      }
      return new Role(filePath, raw);
    }
  }

  toJSON() {
    return {
      id: this.id, name: this.name, active: this.active,
      description: this.description, permissions: this.permissions,
      capabilities: this.capabilities, connectors: this.connectors,
      loadedAt: this.loadedAt, lastModified: this.lastModified,
    };
  }
}

class RoleManager {
  constructor(watchDir, onChange) {
    this.watchDir = watchDir;
    this.onChange = onChange;    // (role, type: 'added'|'changed'|'removed') => void
    this._roles   = new Map();   // id → Role
    this._watchers = [];
    this._debounce = new Map();  // path → timeout
  }

  async watch() {
    await this._scan(this.watchDir);

    const watcher = fs.watch(this.watchDir, { recursive: true }, (event, filename) => {
      if (!filename?.endsWith(EXT)) return;
      const abs = path.join(this.watchDir, filename);
      clearTimeout(this._debounce.get(abs));
      this._debounce.set(abs, setTimeout(() => this._reload(abs, event), 120));
    });
    this._watchers.push(watcher);
  }

  unwatch() {
    this._watchers.forEach(w => w.close());
    this._watchers = [];
  }

  getActive()   { return [...this._roles.values()].filter(r => r.active).map(r => r.toJSON()); }
  getAll()      { return [...this._roles.values()].map(r => r.toJSON()); }
  getRole(id)   { return this._roles.get(id); }

  // ── Private ──────────────────────────────────────────────────────────────

  async _scan(dir) {
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory())                  await this._scan(full);
      else if (e.name.endsWith(EXT))        this._load(full);
    }
  }

  _load(filePath) {
    try {
      const content  = fs.readFileSync(filePath, 'utf8');
      const role     = Role.parse(filePath, content);
      const existed  = this._roles.has(role.id);
      this._roles.set(role.id, role);
      this.onChange?.(role, existed ? 'changed' : 'added');
      return role;
    } catch (err) {
      console.error(`[RoleManager] Failed to load ${filePath}: ${err.message}`);
      return null;
    }
  }

  _reload(filePath, event) {
    const id = path.basename(filePath, EXT);
    if (!fs.existsSync(filePath)) {
      const role = this._roles.get(id);
      if (role) {
        this._roles.delete(id);
        this.onChange?.(role, 'removed');
      }
      return;
    }
    this._load(filePath);
  }
}

module.exports = { RoleManager, Role };
