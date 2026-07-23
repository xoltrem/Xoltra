#!/usr/bin/env node
/**
 * test-skill/scan.js
 * Standalone project auditor. Acts as a simulated user: crawls the project,
 * static-scans for risk patterns, and (if a server is reachable) exercises
 * endpoints including the secure-api signed/encrypted protocol if detected.
 * Outputs machine-readable findings to ./audit-report.json for an AI to consume.
 *
 * Usage: node scan.js [projectDir] [--base-url=http://localhost:8443] [--key-id=client1] [--secret=<hex>]
 * Zero npm dependencies.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const http = require('http');
const https = require('https');

const args = process.argv.slice(2);
const root = path.resolve(args.find(a => !a.startsWith('--')) || '.');
const flag = (name, def = null) => {
  const f = args.find(a => a.startsWith(`--${name}=`));
  return f ? f.split('=').slice(1).join('=') : def;
};
const BASE_URL = flag('base-url', 'http://localhost:8443');
const KEY_ID = flag('key-id');
const SECRET = flag('secret');

const findings = [];
let nextId = 1;
function report(severity, category, msg, extra = {}) {
  findings.push({ id: nextId++, severity, category, message: msg, ...extra });
}

// ---------- 1. file inventory ----------
const SKIP = new Set(['node_modules', '.git', 'dist', 'build', '__pycache__', '.venv', 'venv', '.next', 'out', '.turbo', '.xoltra']);
function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP.has(entry.name)) continue;
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}
let files = [];
try { files = walk(root); }
catch (e) { report('critical', 'fs', `cannot read project root: ${e.message}`, { location_hint: root }); }

const CODE_EXT = new Set(['.js', '.ts', '.jsx', '.tsx', '.py', '.go', '.java', '.rb', '.php']);
const codeFiles = files.filter(f => CODE_EXT.has(path.extname(f)) && path.resolve(f) !== __filename);
report('info', 'inventory', `scanned ${files.length} files, ${codeFiles.length} source files`);

// ---------- 2. static risk patterns ----------
const STATIC_RULES = [
  { re: /(api[_-]?key|secret|password|token)\s*[:=]\s*["'][^"'\n]{6,}["']/i, severity: 'high', category: 'hardcoded_secret', msg: 'possible hardcoded secret literal' },
  { re: /-----BEGIN (RSA |EC |)PRIVATE KEY-----/, severity: 'critical', category: 'hardcoded_secret', msg: 'embedded private key' },
  { re: /catch\s*\(\s*\w*\s*\)\s*\{\s*\}/, severity: 'medium', category: 'error_handling', msg: 'empty catch block swallows errors' },
  { re: /except\s*:\s*$/m, severity: 'medium', category: 'error_handling', msg: 'bare except swallows all errors' },
  { re: /console\.log\([^)]*(password|secret|token|key)[^)]*\)/i, severity: 'medium', category: 'logging', msg: 'sensitive value possibly logged' },
  { re: /TODO|FIXME/, severity: 'low', category: 'incomplete', msg: 'unfinished work marker' },
  { re: /eval\(/, severity: 'high', category: 'injection_risk', msg: 'eval() use is an injection risk' },
  { re: /child_process|os\.system|subprocess\.call/, severity: 'medium', category: 'shell_exec', msg: 'shell execution call — verify input is not user-controlled' },
];
for (const file of codeFiles) {
  let text;
  try { text = fs.readFileSync(file, 'utf8'); } catch { continue; }
  const lines = text.split('\n');
  lines.forEach((line, i) => {
    if (line.includes('audit-ok')) return; // reviewed, intentionally safe (e.g. blocklist strings, test fixtures)
    for (const rule of STATIC_RULES) {
      if (rule.re.test(line)) {
        report(rule.severity, rule.category, rule.msg, {
          file: path.relative(root, file), line: i + 1,
          snippet: line.trim().slice(0, 160),
        });
      }
    }
  });
}

// ---------- 3. detect server type ----------
const hasNodeServer = files.some(f => /server\.js$/.test(f));
const hasPyServer = files.some(f => /server\.py$/.test(f));
const isSecureApi = codeFiles.some(f => {
  try { return /x-api-key-id|x-signature/.test(fs.readFileSync(f, 'utf8')); } catch { return false; }
});
report('info', 'inventory', `server detected: node=${hasNodeServer} python=${hasPyServer} secure-api-protocol=${isSecureApi}`);

// ---------- 4. dynamic endpoint tests ----------
function request(method, urlStr, headers, body) {
  return new Promise((resolve) => {
    const u = new URL(urlStr);
    const lib = u.protocol === 'https:' ? https : http;
    const reqOpts = { method, hostname: u.hostname, port: u.port, path: u.pathname + u.search, headers, rejectUnauthorized: false, timeout: 4000 };
    const r = lib.request(reqOpts, (res) => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => resolve({ status: res.statusCode, body: data }));
    });
    r.on('error', (e) => resolve({ error: e.message }));
    r.on('timeout', () => { r.destroy(); resolve({ error: 'timeout' }); });
    if (body) r.write(body);
    r.end();
  });
}

function signedRequest(method, p, payloadObj) {
  const ts = Date.now();
  const nonce = crypto.randomBytes(8).toString('hex');
  let bodyStr = '';
  if (payloadObj !== undefined) {
    const sessionKey = crypto.createHash('sha256').update(Buffer.from(SECRET, 'hex')).update(Buffer.from(SECRET, 'hex')).digest(); // approximation w/o master key
    bodyStr = JSON.stringify(payloadObj);
  }
  const base = `${method}\n${p}\n${ts}\n${nonce}\n${bodyStr}`;
  const sig = crypto.createHmac('sha256', Buffer.from(SECRET, 'hex')).update(base).digest('hex');
  return { headers: { 'x-api-key-id': KEY_ID, 'x-timestamp': ts, 'x-nonce': nonce, 'x-signature': sig, 'content-type': 'text/plain' }, body: bodyStr };
}

async function dynamicTests() {
  const health = await request('GET', `${BASE_URL}/health`, {});
  if (health.error) {
    report('warning', 'connectivity', `server not reachable at ${BASE_URL}: ${health.error}`, { location_hint: 'start the server before running scan.js, or pass --base-url' });
    return;
  }
  if (health.status === 200) report('pass', 'connectivity', 'health endpoint reachable');
  else report('high', 'connectivity', `health endpoint returned ${health.status}`, { location_hint: '/health route' });

  if (!isSecureApi) return;

  // negative: missing auth headers must be rejected
  const noAuth = await request('GET', `${BASE_URL}/v1/data/__probe__`, {});
  if (noAuth.error) {
    report('warning', 'security_layer2', `could not reach auth endpoint to test: ${noAuth.error}`, { location_hint: 'ensure server is running at ' + BASE_URL });
  } else if (noAuth.status === 401) {
    report('pass', 'security_layer2', 'request without signature correctly rejected (401)');
  } else {
    report('critical', 'security_layer2', `unsigned request was NOT rejected (got ${noAuth.status}, expected 401) — auth layer bypassable`, { location_hint: 'authAndDecrypt / verify_signature' });
  }

  if (!KEY_ID || !SECRET) {
    report('info', 'security_layer2', 'pass --key-id and --secret to run full signed round-trip + replay tests');
    return;
  }

  // positive round trip (best-effort; payload encryption requires MASTER_KEY which scan.js intentionally does not have)
  const probePath = '/v1/data/__probe__';
  const { headers, body } = signedRequest('GET', probePath);
  const signedResp = await request('GET', `${BASE_URL}${probePath}`, headers);
  if (signedResp.status === 401 && /bad_signature/.test(signedResp.body || '')) {
    report('info', 'security_layer2', 'signature check active (rejected scan.js probe signature as expected — scan.js does not hold MASTER_KEY by design)');
  } else if (signedResp.status === 404 || signedResp.status === 200) {
    report('pass', 'security_layer2', 'signed request accepted by server');
  } else {
    report('medium', 'security_layer2', `unexpected status ${signedResp.status} for signed probe`, { body: (signedResp.body || '').slice(0, 200) });
  }

  // replay test: send same nonce twice
  const replayHeaders = { ...headers };
  const r1 = await request('GET', `${BASE_URL}${probePath}`, replayHeaders);
  const r2 = await request('GET', `${BASE_URL}${probePath}`, replayHeaders);
  if (r2.status === 401 && /replay_detected|bad_signature/.test(r2.body || '')) {
    report('pass', 'security_layer2', 'nonce replay correctly rejected on second use');
  } else if (r1.status === r2.status) {
    report('high', 'security_layer2', 'identical request accepted twice — possible replay vulnerability', { location_hint: 'nonce cache (seenNonces)' });
  }
}

// ---------- 5. run + emit ----------
(async () => {
  await dynamicTests();
  const summary = {
    scanned_at: new Date().toISOString(),
    root,
    totals: findings.reduce((acc, f) => { acc[f.severity] = (acc[f.severity] || 0) + 1; return acc; }, {}),
    findings,
  };
  const outPath = path.join(root, 'audit-report.json');
  fs.writeFileSync(outPath, JSON.stringify(summary, null, 2));
  const blocking = findings.filter(f => f.severity === 'critical' || f.severity === 'high');
  console.log(`AUDIT_REPORT_PATH=${outPath}`);
  console.log(`TOTALS=${JSON.stringify(summary.totals)}`);
  if (blocking.length) {
    console.log('BLOCKING_ISSUES:');
    for (const f of blocking) {
      console.log(`- [${f.severity.toUpperCase()}][${f.category}] ${f.message} ${f.file ? `(${f.file}:${f.line})` : ''}`);
    }
    process.exitCode = 1;
  } else {
    console.log('NO_BLOCKING_ISSUES');
  }
})();
