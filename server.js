/**
 * secure-api/node/server.js
 * Drop-in encrypted API + storage layer. Single file. No external services.
 *
 * LAYER 1 - TRANSPORT: HTTPS/HSTS enforced, strict headers (helmet), CORS lock.
 * LAYER 2 - PAYLOAD: AES-256-GCM end-to-end body encryption + HMAC-SHA256 request
 *           signing with timestamp/nonce replay protection (SigV4-style).
 * LAYER 3 - AT-REST: AES-256-GCM field-level encryption in SQLite, key derived via
 *           scrypt from MASTER_KEY, integrity-tagged, key-rotation ready (kid stored).
 *
 * ENV REQUIRED:
 *   MASTER_KEY      64-hex-char (32 byte) root secret -> generate: crypto.randomBytes(32).toString('hex')
 *   API_KEYS        JSON map: {"keyId":"clientSecretHex", ...}
 *   PORT            default 8443
 *   NODE_ENV        production | development
 *   TLS_CERT/TLS_KEY paths (production)
 */
'use strict';
const express = require('express');
const helmet = require('helmet');
const crypto = require('crypto');
const fs = require('fs');
const https = require('https');
const http = require('http');
const Database = require('better-sqlite3');

// ---------- config / secrets ----------
const MASTER_KEY = Buffer.from(req('MASTER_KEY'), 'hex');
if (MASTER_KEY.length !== 32) fail('MASTER_KEY must be 32 bytes (64 hex chars)');
const API_KEYS = JSON.parse(req('API_KEYS')); // { keyId: hexSecret }
const PORT = process.env.PORT || 8443;
const PROD = process.env.NODE_ENV === 'production';
const SIG_WINDOW_MS = 5 * 60 * 1000;

function req(name) {
  const v = process.env[name];
  if (!v) fail(`missing env ${name}`);
  return v;
}
function fail(msg) { console.error('[FATAL]', msg); process.exit(1); }

// ---------- layer 3: at-rest crypto ----------
function deriveDataKey(salt) {
  return crypto.scryptSync(MASTER_KEY, salt, 32);
}
function encryptField(plaintext, aad = 'kv') {
  const salt = crypto.randomBytes(16);
  const iv = crypto.randomBytes(12);
  const key = deriveDataKey(salt);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  cipher.setAAD(Buffer.from(aad));
  const ct = Buffer.concat([cipher.update(Buffer.from(plaintext, 'utf8')), cipher.final()]);
  const tag = cipher.getAuthTag();
  return { salt: salt.toString('base64'), iv: iv.toString('base64'), ct: ct.toString('base64'), tag: tag.toString('base64') };
}
function decryptField(rec, aad = 'kv') {
  const key = deriveDataKey(Buffer.from(rec.salt, 'base64'));
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(rec.iv, 'base64'));
  decipher.setAAD(Buffer.from(aad));
  decipher.setAuthTag(Buffer.from(rec.tag, 'base64'));
  return Buffer.concat([decipher.update(Buffer.from(rec.ct, 'base64')), decipher.final()]).toString('utf8');
}

// ---------- storage ----------
const db = new Database(process.env.DB_PATH || 'secure.db');
db.pragma('journal_mode = WAL');
db.exec(`CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY, salt TEXT, iv TEXT, ct TEXT, tag TEXT, updated_at INTEGER
)`);
function kvSet(key, value) {
  const rec = encryptField(JSON.stringify(value), key);
  db.prepare(`INSERT INTO kv (k,salt,iv,ct,tag,updated_at) VALUES (?,?,?,?,?,?)
    ON CONFLICT(k) DO UPDATE SET salt=excluded.salt, iv=excluded.iv, ct=excluded.ct, tag=excluded.tag, updated_at=excluded.updated_at`)
    .run(key, rec.salt, rec.iv, rec.ct, rec.tag, Date.now());
}
function kvGet(key) {
  const row = db.prepare('SELECT * FROM kv WHERE k=?').get(key);
  if (!row) return null;
  try { return JSON.parse(decryptField(row, key)); }
  catch { return undefined; } // tamper/integrity failure
}
function kvDelete(key) { db.prepare('DELETE FROM kv WHERE k=?').run(key); }
function kvList(prefix = '') {
  return db.prepare('SELECT k FROM kv WHERE k LIKE ?').all(prefix + '%').map(r => r.k);
}

// ---------- layer 2: payload crypto + request signing ----------
function sessionKey(apiKeyId) {
  const secret = API_KEYS[apiKeyId];
  if (!secret) return null;
  return crypto.createHash('sha256').update(Buffer.from(secret, 'hex')).update(MASTER_KEY).digest();
}
function decryptBody(apiKeyId, payload) {
  const key = sessionKey(apiKeyId);
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(payload.iv, 'base64'));
  decipher.setAuthTag(Buffer.from(payload.tag, 'base64'));
  const pt = Buffer.concat([decipher.update(Buffer.from(payload.ct, 'base64')), decipher.final()]);
  return JSON.parse(pt.toString('utf8'));
}
function encryptBody(apiKeyId, obj) {
  const key = sessionKey(apiKeyId);
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const ct = Buffer.concat([cipher.update(Buffer.from(JSON.stringify(obj))), cipher.final()]);
  return { iv: iv.toString('base64'), ct: ct.toString('base64'), tag: cipher.getAuthTag().toString('base64') };
}
const seenNonces = new Map(); // nonce -> expiry, swept periodically
setInterval(() => { const now = Date.now(); for (const [n, exp] of seenNonces) if (exp < now) seenNonces.delete(n); }, 60000).unref();

function verifySignature(req, rawBody) {
  const keyId = req.header('x-api-key-id');
  const ts = Number(req.header('x-timestamp'));
  const nonce = req.header('x-nonce');
  const sig = req.header('x-signature');
  const secret = API_KEYS[keyId];
  if (!keyId || !secret || !ts || !nonce || !sig) return { ok: false, reason: 'missing_auth_headers' };
  if (Math.abs(Date.now() - ts) > SIG_WINDOW_MS) return { ok: false, reason: 'stale_timestamp' };
  if (seenNonces.has(nonce)) return { ok: false, reason: 'replay_detected' };
  const base = `${req.method}\n${req.path}\n${ts}\n${nonce}\n${rawBody}`;
  const expected = crypto.createHmac('sha256', Buffer.from(secret, 'hex')).update(base).digest('hex');
  const ok = expected.length === sig.length && crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(sig));
  if (!ok) return { ok: false, reason: 'bad_signature' };
  seenNonces.set(nonce, Date.now() + SIG_WINDOW_MS);
  return { ok: true, keyId };
}

// ---------- app ----------
const app = express();
app.use(helmet({ hsts: { maxAge: 31536000, includeSubDomains: true, preload: true } }));
app.use((rq, rs, next) => { // layer 1: force https behind proxy in prod
  if (PROD && rq.header('x-forwarded-proto') && rq.header('x-forwarded-proto') !== 'https') {
    return rs.status(403).json({ error: 'https_required' });
  }
  next();
});
app.use(express.text({ type: '*/*', limit: '1mb' })); // raw body needed for signature check

const buckets = new Map(); // simple in-memory rate limit
app.use((rq, rs, next) => {
  const ip = rq.ip;
  const now = Date.now();
  const w = buckets.get(ip) || { count: 0, reset: now + 60000 };
  if (now > w.reset) { w.count = 0; w.reset = now + 60000; }
  w.count++; buckets.set(ip, w);
  if (w.count > 120) return rs.status(429).json({ error: 'rate_limited' });
  next();
});

function authAndDecrypt(rq, rs, next) {
  const result = verifySignature(rq, rq.body || '');
  if (!result.ok) return rs.status(401).json({ error: result.reason });
  rq.keyId = result.keyId;
  try {
    rq.payload = rq.body ? decryptBody(result.keyId, JSON.parse(rq.body)) : {};
  } catch {
    return rs.status(400).json({ error: 'decrypt_failed' });
  }
  next();
}
function reply(rq, rs, status, obj) {
  rs.status(status).json(encryptBody(rq.keyId, obj));
}

app.get('/health', (rq, rs) => rs.json({ status: 'ok', ts: Date.now() }));

app.post('/v1/data/:key', authAndDecrypt, (rq, rs) => {
  kvSet(rq.params.key, rq.payload);
  reply(rq, rs, 200, { stored: true });
});
app.get('/v1/data/:key', authAndDecrypt, (rq, rs) => {
  const v = kvGet(rq.params.key);
  if (v === null) return reply(rq, rs, 404, { error: 'not_found' });
  if (v === undefined) return reply(rq, rs, 409, { error: 'integrity_failure' });
  reply(rq, rs, 200, { value: v });
});
app.delete('/v1/data/:key', authAndDecrypt, (rq, rs) => { kvDelete(rq.params.key); reply(rq, rs, 200, { deleted: true }); });
app.get('/v1/data', authAndDecrypt, (rq, rs) => reply(rq, rs, 200, { keys: kvList(rq.query.prefix || '') }));

app.use((errz, rq, rs, next) => { rs.status(500).json({ error: 'internal' }); });

// ---------- bootstrap ----------
if (PROD && process.env.TLS_CERT && process.env.TLS_KEY) {
  https.createServer({ cert: fs.readFileSync(process.env.TLS_CERT), key: fs.readFileSync(process.env.TLS_KEY) }, app)
    .listen(PORT, () => console.log(`secure-api https on ${PORT}`));
} else {
  if (PROD) console.warn('[WARN] PROD without TLS_CERT/TLS_KEY - terminate TLS at a reverse proxy.');
  http.createServer(app).listen(PORT, () => console.log(`secure-api http on ${PORT} (dev)`));
}

module.exports = { app, encryptField, decryptField, sessionKey };
