/**
 * Xoltra Agent Core
 * Long-running persistent agent with task queue, checkpointing, and resume
 */

'use strict';
const EventEmitter = require('events');
const { StateManager } = require('../state/persistence');
const { ConnectorRegistry } = require('../connectors');
const { RoleManager } = require('../roles/role_manager');
const { WorkflowBuilder } = require('../workflow/builder');

const AgentStatus = Object.freeze({ IDLE: 'IDLE', RUNNING: 'RUNNING', PAUSED: 'PAUSED', RESUMING: 'RESUMING', OFFLINE: 'OFFLINE', ERROR: 'ERROR' });
const TaskStatus  = Object.freeze({ PENDING: 'PENDING', RUNNING: 'RUNNING', PAUSED: 'PAUSED', DONE: 'DONE', FAILED: 'FAILED' });

// ── Task ──────────────────────────────────────────────────────────────────────

class Task {
  constructor({ id, title, connector, instructions, priority = 0 } = {}) {
    this.id           = id || `task_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    this.title        = title;
    this.connector    = connector;
    this.instructions = instructions;
    this.priority     = priority;
    this.status       = TaskStatus.PENDING;
    this.progress     = 0;
    this.steps        = [];
    this.currentStep  = 0;
    this.createdAt    = Date.now();
    this.startedAt    = null;
    this.completedAt  = null;
    this.checkpoint   = null;
    this.result       = null;
    this.error        = null;
    this.summary      = null;
  }

  saveCheckpoint(data) {
    this.checkpoint = { step: this.currentStep, data, savedAt: Date.now() };
  }

  toJSON() {
    return {
      id: this.id, title: this.title, connector: this.connector,
      instructions: this.instructions, priority: this.priority,
      status: this.status, progress: this.progress, steps: this.steps,
      currentStep: this.currentStep, createdAt: this.createdAt,
      startedAt: this.startedAt, completedAt: this.completedAt,
      checkpoint: this.checkpoint, result: this.result,
      error: this.error, summary: this.summary,
    };
  }

  static fromJSON(data) {
    const t = new Task(data);
    return Object.assign(t, data);
  }
}

// ── XoltraAgent ───────────────────────────────────────────────────────────────

class XoltraAgent extends EventEmitter {
  constructor({ stateDir = '.xoltra', permissions = {}, maxConcurrent = 3 } = {}) {
    super();
    this.stateDir         = stateDir;
    this.status           = AgentStatus.IDLE;
    this.taskQueue        = [];
    this.activeTasks      = new Map();       // id → Task
    this.completedTasks   = [];
    this.summaries        = [];
    this.permissions      = { workflow: true, ...permissions }; // workflow always on when role active
    this.maxConcurrent    = maxConcurrent;
    this._tickHandle      = null;
    this._online          = true;

    this.state     = new StateManager(stateDir);
    this.connectors = new ConnectorRegistry(this.permissions);
    this.roles     = new RoleManager(stateDir, this._onRoleChange.bind(this));
    this.workflows = new WorkflowBuilder(this.connectors);
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  async start() {
    this.emit('log', '🟢 Starting Xoltra...');
    await this.state.init();
    await this._loadAndResume();
    await this.roles.watch();
    this.status = AgentStatus.RUNNING;
    this.emit('status', this.status);
    this._startTick();
    this.emit('log', `Agent running · ${this.taskQueue.length} tasks in queue`);
  }

  async pause() {
    if (this.status === AgentStatus.PAUSED) return;
    this._stopTick();
    this.status = AgentStatus.PAUSED;
    for (const task of this.activeTasks.values()) task.status = TaskStatus.PAUSED;
    await this._saveState();
    this.emit('status', this.status);
    this.emit('log', '⏸ Agent paused · state saved to .xoltra/');
  }

  async resume() {
    if (this.status !== AgentStatus.PAUSED) return;
    this.status = AgentStatus.RESUMING;
    this.emit('status', this.status);
    // Re-queue paused active tasks at front
    for (const task of this.activeTasks.values()) {
      task.status = TaskStatus.PENDING;
      this.taskQueue.unshift(task);
    }
    this.activeTasks.clear();
    this.status = AgentStatus.RUNNING;
    this._startTick();
    this.emit('status', this.status);
    this.emit('log', '▶️ Agent resumed');
  }

  async stop() {
    await this.pause();
    this.roles.unwatch();
    this.status = AgentStatus.IDLE;
    this.emit('status', this.status);
    this.emit('log', '⏹ Agent stopped');
  }

  // ── Task management ────────────────────────────────────────────────────────

  async addTask(taskData) {
    const task = new Task(taskData);
    this.taskQueue.push(task);
    this.taskQueue.sort((a, b) => b.priority - a.priority);
    await this._saveState();
    this.emit('task:added', task.toJSON());
    this.emit('log', `➕ Task added: "${task.title}" [${task.id}]`);
    return task;
  }

  async cancelTask(taskId) {
    this.taskQueue = this.taskQueue.filter(t => t.id !== taskId);
    if (this.activeTasks.has(taskId)) {
      const task = this.activeTasks.get(taskId);
      task.status = TaskStatus.FAILED;
      task.error = 'Cancelled by user';
      this.activeTasks.delete(taskId);
    }
    await this.state.clearCheckpoint(taskId);
    await this._saveState();
    this.emit('task:cancelled', taskId);
    this.emit('log', `❌ Task cancelled: ${taskId}`);
  }

  // ── Permissions ────────────────────────────────────────────────────────────

  grantPermission(connectorId) {
    this.permissions[connectorId] = true;
    this.connectors.updatePermissions(this.permissions);
    this.emit('permission:changed', { connectorId, granted: true });
    this.emit('log', `🔓 Permission granted: ${connectorId}`);
  }

  revokePermission(connectorId) {
    this.permissions[connectorId] = false;
    this.connectors.updatePermissions(this.permissions);
    this.emit('permission:changed', { connectorId, granted: false });
    this.emit('log', `🔒 Permission revoked: ${connectorId}`);
  }

  // ── Inspect ────────────────────────────────────────────────────────────────

  getStatus() {
    return {
      status      : this.status,
      activeTasks : [...this.activeTasks.values()].map(t => t.toJSON()),
      queuedTasks : this.taskQueue.map(t => t.toJSON()),
      completed   : this.completedTasks.slice(-20),
      summaries   : this.summaries.slice(-20),
      permissions : this.permissions,
      roles       : this.roles.getActive(),
      stateInfo   : this.state.getInfo(),
      workflows   : this.workflows.list(),
    };
  }

  // ── Private: tick + task runner ────────────────────────────────────────────

  _startTick() {
    this._tickHandle = setInterval(() => this._tick(), 400);
  }

  _stopTick() {
    clearInterval(this._tickHandle);
    this._tickHandle = null;
  }

  async _tick() {
    if (this.status !== AgentStatus.RUNNING) return;
    while (this.activeTasks.size < this.maxConcurrent && this.taskQueue.length > 0) {
      const task = this.taskQueue.shift();
      task.status = TaskStatus.RUNNING;
      task.startedAt = Date.now();
      this.activeTasks.set(task.id, task);
      this.emit('task:started', task.toJSON());
      this._runTask(task).catch(err => this._handleError(task, err));
    }
  }

  async _runTask(task) {
    const connector = this.connectors.get(task.connector);
    if (!connector)              throw new Error(`No connector: ${task.connector}`);
    if (!this.permissions[task.connector]) throw new Error(`No permission: ${task.connector}`);

    this.emit('log', `⚙️ Running: "${task.title}" via ${task.connector}`);
    const steps = await connector.planSteps(task.instructions);
    task.steps = steps.map(s => s.label);
    const startFrom = task.checkpoint?.step ?? 0;

    for (let i = startFrom; i < steps.length; i++) {
      // Respect pause
      if (this.status === AgentStatus.PAUSED) {
        task.saveCheckpoint({ step: i });
        await this.state.saveCheckpoint(task.id, task.checkpoint);
        return;
      }

      task.currentStep = i;
      task.progress    = Math.round((i / steps.length) * 100);
      this.emit('task:progress', task.toJSON());

      try {
        const result = await connector.executeStep(steps[i], task);
        if (result?.checkpoint) {
          task.saveCheckpoint(result.checkpoint);
          await this.state.saveCheckpoint(task.id, task.checkpoint);
        }
      } catch (err) {
        task.saveCheckpoint({ step: i, errorMsg: err.message });
        await this.state.saveCheckpoint(task.id, task.checkpoint);
        throw err;
      }

      await new Promise(r => setTimeout(r, 100)); // yield
    }

    await this._completeTask(task);
  }

  async _completeTask(task) {
    task.status      = TaskStatus.DONE;
    task.progress    = 100;
    task.completedAt = Date.now();
    task.checkpoint  = null;
    const dur        = Math.floor((task.completedAt - task.startedAt) / 1000);
    task.summary     = `Completed ${task.steps.length} steps in ${dur}s via ${task.connector}.`;
    this.summaries.unshift({
      id: `sum_${task.id}`, taskTitle: task.title, completedAt: task.completedAt,
      connector: task.connector, summary: task.summary,
      duration: `${Math.floor(dur / 60)}m ${dur % 60}s`,
    });
    this.activeTasks.delete(task.id);
    this.completedTasks.push(task.toJSON());
    await this.state.clearCheckpoint(task.id);
    await this._saveState();
    this.emit('task:done', task.toJSON());
    this.emit('log', `✅ Done: "${task.title}"`);
  }

  _handleError(task, err) {
    task.status = TaskStatus.FAILED;
    task.error  = err.message;
    this.activeTasks.delete(task.id);
    this.emit('task:error', { task: task.toJSON(), error: err.message });
    this.emit('log', `❌ Failed: "${task.title}" — ${err.message}`);
  }

  // ── Private: state ─────────────────────────────────────────────────────────

  async _loadAndResume() {
    this.status = AgentStatus.RESUMING;
    const saved = await this.state.load();
    if (!saved) { this.emit('log', 'No saved state — starting fresh'); return; }

    this.taskQueue      = (saved.taskQueue || []).map(Task.fromJSON);
    this.completedTasks = saved.completedTasks || [];
    this.summaries      = saved.summaries      || [];
    this.permissions    = { ...this.permissions, ...saved.permissions };

    // Re-queue previously active tasks (they have checkpoints)
    for (const td of (saved.activeTasks || [])) {
      const task = Task.fromJSON(td);
      task.status = TaskStatus.PENDING;
      this.taskQueue.unshift(task);
    }
    this.emit('log', `🔄 Resumed: ${this.taskQueue.length} tasks restored`);
  }

  async _saveState() {
    await this.state.save({
      taskQueue    : this.taskQueue.map(t => t.toJSON()),
      activeTasks  : [...this.activeTasks.values()].map(t => t.toJSON()),
      completedTasks: this.completedTasks.slice(-50),
      summaries    : this.summaries.slice(-50),
      permissions  : this.permissions,
      savedAt      : Date.now(),
    });
  }

  // ── Private: role watcher callback ─────────────────────────────────────────

  _onRoleChange(role, type) {
    this.emit('log', `📄 Role ${type}: ${role.name}`);
    if (type !== 'removed' && Array.isArray(role.permissions)) {
      role.permissions.forEach(p => this.grantPermission(p));
    }
    this.emit('role:changed', { role, type });
  }
}

module.exports = { XoltraAgent, Task, AgentStatus, TaskStatus };
