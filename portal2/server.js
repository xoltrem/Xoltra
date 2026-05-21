const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const storage = require('./src/storage');
const summarizer = require('./src/summarizer');
const Monitor = require('./src/monitor');

const app = express();
app.use(express.json({ limit: '5mb' }));
app.use(express.static(path.join(__dirname, 'public')));

const monitor = new Monitor();

// stream logs to frontend via SSE
const sseClients = new Set();
app.get('/api/events', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  sseClients.add(res);
  req.on('close', () => sseClients.delete(res));
});
function send(type, data) {
  const msg = `data: ${JSON.stringify({ type, ...data })}\n\n`;
  sseClients.forEach(c => c.write(msg));
}

monitor.onLog = (msg, level) => send('log', { msg, level });
monitor.onTriggered = () => send('triggered', { msg: 'duck.ai opened!' });
monitor.onStopped = () => send('status', { running: false });

// Auto monitor
app.post('/api/auto/start', async (req, res) => {
  try {
    await monitor.start();
    send('status', { running: true });
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/auto/stop', async (req, res) => {
  await monitor.stop();
  res.json({ ok: true });
});

app.get('/api/auto/status', (req, res) => {
  res.json({ running: monitor.isRunning() });
});

// Open duck.ai manually in incognito
app.post('/api/open-duck', (req, res) => {
  const url = 'https://duck.ai/';
  const p = process.platform;
  const cmds = p === 'win32'
    ? [['cmd',['/c','start','chrome','--incognito',url]],['cmd',['/c','start','msedge','--inprivate',url]],['cmd',['/c','start','firefox','--private-window',url]]]
    : p === 'darwin'
    ? [['open',['-na','Google Chrome','--args','--incognito',url]],['open',['-na','Brave Browser','--args','--incognito',url]],['open',['-na','Firefox','--args','--private-window',url]]]
    : [['google-chrome',['--incognito',url]],['chromium-browser',['--incognito',url]],['brave-browser',['--incognito',url]],['firefox',['--private-window',url]]];

  let done = false;
  function tryNext(i) {
    if (i >= cmds.length) { if (!done) res.status(500).json({ error: 'No browser found. Open duck.ai manually.' }); return; }
    const [cmd, args] = cmds[i];
    const proc = spawn(cmd, args, { detached: true, stdio: 'ignore', shell: p === 'win32' });
    proc.on('error', () => tryNext(i + 1));
    proc.on('spawn', () => { if (!done) { done = true; res.json({ ok: true }); } proc.unref(); });
  }
  tryNext(0);
});

// Summarize
app.post('/api/summarize', async (req, res) => {
  const { content } = req.body;
  if (!content?.trim()) return res.status(400).json({ error: 'No content provided' });
  try {
    const result = await summarizer.summarize(content);
    res.json(storage.addSummary(result));
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// Settings
app.get('/api/settings', (req, res) => { const s = storage.getSettings(); res.json({ cohereKeySet: !!s.cohereApiKey }); });
app.post('/api/settings', (req, res) => { storage.saveSettings(req.body); res.json({ ok: true }); });
app.post('/api/settings/test', async (req, res) => res.json(await summarizer.testKey()));

// Summaries
app.get('/api/summaries', (req, res) => res.json(storage.getSummaries()));
app.delete('/api/summaries/:id', (req, res) => { storage.deleteSummary(req.params.id); res.json({ ok: true }); });
app.delete('/api/summaries', (req, res) => { storage.clearSummaries(); res.json({ ok: true }); });

app.listen(3000, () => console.log('\n  🌀 Portal → http://localhost:3000\n'));
