// src/monitor.js
// Opens claude.ai in a browser window, watches for usage limit,
// then opens https://duck.ai/ in a new incognito window automatically.

const { spawn } = require('child_process');
let puppeteer;
try { puppeteer = require('puppeteer'); } catch { puppeteer = null; }

const DUCK_URL = 'https://duck.ai/';
const CHECK_INTERVAL = 4000; // ms

const LIMIT_PHRASES = [
  "you've reached your usage limit",
  "reached your usage limit",
  "usage limit reached",
  "you've hit your usage",
  "daily usage limit",
  "usage limits reset",
  "free usage limit",
  "upgrade to claude pro",
  "upgrade your plan to continue",
  "message limit",
  "reply limit"
];

class Monitor {
  constructor() {
    this.browser = null;
    this.page = null;
    this.interval = null;
    this.running = false;
    this.onLog = null;
    this.onTriggered = null;
    this.onStopped = null;
  }

  async start() {
    if (!puppeteer) throw new Error('Run npm install first');
    if (this.running) return;

    this.running = true;
    this._log('Launching Claude tab...');

    this.browser = await puppeteer.launch({
      headless: false,
      defaultViewport: null,
      args: ['--start-maximized', '--no-sandbox', '--disable-blink-features=AutomationControlled'],
      ignoreDefaultArgs: ['--enable-automation']
    });

    this.page = (await this.browser.pages())[0] || await this.browser.newPage();

    // Hide automation flags
    await this.page.evaluateOnNewDocument(() => {
      Object.defineProperty(navigator, 'webdriver', { get: () => false });
    });

    await this.page.goto('https://claude.ai', { waitUntil: 'networkidle2', timeout: 30000 });
    this._log('Watching for usage limit on claude.ai...');

    this.browser.on('disconnected', () => {
      if (this.running) { this.running = false; if (this.onStopped) this.onStopped(); }
    });

    // Poll for usage limit
    this.interval = setInterval(async () => {
      if (!this.running || !this.page) return;
      try {
        const hit = await this._checkLimit();
        if (hit) {
          clearInterval(this.interval);
          this.interval = null;
          this._log('Usage limit detected — opening duck.ai in incognito...');
          await this._openDuckAI();
          if (this.onTriggered) this.onTriggered();
          this.running = false;
          if (this.onStopped) this.onStopped();
        }
      } catch { /* page navigated */ }
    }, CHECK_INTERVAL);
  }

  async stop() {
    this.running = false;
    if (this.interval) { clearInterval(this.interval); this.interval = null; }
    if (this.browser) {
      try { await this.browser.close(); } catch {}
      this.browser = null; this.page = null;
    }
    this._log('Auto monitor stopped.');
    if (this.onStopped) this.onStopped();
  }

  async _checkLimit() {
    return this.page.evaluate((phrases) => {
      const text = (document.body?.innerText || '').toLowerCase();
      return phrases.some(p => text.includes(p));
    }, LIMIT_PHRASES);
  }

  async _openDuckAI() {
    const platform = process.platform;
    const url = DUCK_URL;

    const commands = platform === 'win32'
      ? [
          ['cmd', ['/c', 'start', 'chrome', '--incognito', url]],
          ['cmd', ['/c', 'start', 'msedge', '--inprivate', url]],
          ['cmd', ['/c', 'start', 'firefox', '--private-window', url]],
        ]
      : platform === 'darwin'
      ? [
          ['open', ['-na', 'Google Chrome', '--args', '--incognito', url]],
          ['open', ['-na', 'Brave Browser', '--args', '--incognito', url]],
          ['open', ['-na', 'Firefox', '--args', '--private-window', url]],
        ]
      : [
          ['google-chrome', ['--incognito', url]],
          ['chromium-browser', ['--incognito', url]],
          ['brave-browser', ['--incognito', url]],
          ['firefox', ['--private-window', url]],
        ];

    for (const [cmd, args] of commands) {
      const ok = await new Promise(resolve => {
        const p = spawn(cmd, args, { detached: true, stdio: 'ignore', shell: platform === 'win32' });
        p.on('spawn', () => { p.unref(); resolve(true); });
        p.on('error', () => resolve(false));
      });
      if (ok) { this._log('duck.ai opened in incognito ✓'); return; }
    }
    this._log('Could not open browser automatically — open duck.ai manually', 'warn');
  }

  _log(msg, level = 'info') {
    console.log(`[Monitor] ${msg}`);
    if (this.onLog) this.onLog(msg, level);
  }

  isRunning() { return this.running; }
}

module.exports = Monitor;
