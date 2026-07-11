/**
 * secure-api/node/server.js
 * Drop-in encrypted API + storage layer. Upstash Redis Serverless Version.
 */
'use strict';
const express = require('express');
const helmet = require('helmet');
const crypto = require('crypto');
const fs = require('fs');
const { Redis } = require('@upstash/redis');

// ---------- config / secrets ----------
let MASTER_KEY;
try {
  MASTER_KEY = Buffer.from(process.env.MASTER_KEY || '', 'hex');
} catch (e) {
  console.error('[FATAL] MASTER_KEY parsing failed');
}

const API_KEYS = {
  client1: process.env.CLIENT_ONE,
  client2: process.env.CLIENT_TWO
};

const PROD = process.env.NODE_ENV === 'production';
const SIG_WINDOW_MS = 5 * 60 * 1000;

// Initialize Upstash safely
let kv;
try {
  kv = Redis.fromEnv();
} catch (e) {
  console.error('[WARN] Upstash environment variables missing initialization configuration.');
}

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
async function kvSet(key, value) {
  const rec = encryptField(JSON.stringify(value), key);
  await kv.set(key, rec);
}
async function kvGet(key) {
  const row = await kv.get(key);
  if (!row) return null;
  try { return JSON.parse(decryptField(row, key)); }
  catch { return undefined; }
}
async function kvDelete(key) {
  await kv.del(key);
}

// ---------- layer 2: payload crypto + request signing ----------
function sessionKey(apiKeyId) {
  const secret = API_KEYS[apiKeyId];
  if (!secret || !MASTER_KEY || MASTER_KEY.length !== 32) return null;
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
const seenNonces = new Map();
setInterval(() => { const now = Date.now(); for (const [n, exp] of seenNonces) if (exp < now) seenNonces.delete(n); }, 60000).unref();

function verifySignature(req, rawBody) {
  const keyId = req.header('x-api-key-id');
  const ts = Number(req.header('x-timestamp'));
  const nonce = req.header('x-nonce');
  const sig = req.header('x-signature');
  const secret = API_KEYS[keyId];
  if (!MASTER_KEY || MASTER_KEY.length !== 32) return { ok: false, reason: 'server_missing_master_key' };
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

// Fast environment safety gate
app.use((rq, rs, next) => {
  if (!process.env.MASTER_KEY || !process.env.CLIENT_ONE) {
    return rs.status(500).json({ error: 'configuration_error', details: 'Missing required environment keys on host.' });
  }
  if (PROD && rq.header('x-forwarded-proto') && rq.header('x-forwarded-proto') !== 'https') {
    return rs.status(403).json({ error: 'https_required' });
  }
  next();
});

app.use(express.text({ type: '*/*', limit: '1mb' }));

const buckets = new Map();
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

app.post('/v1/data/:key', authAndDecrypt, async (rq, rs, next) => {
  try {
    await kvSet(rq.params.key, rq.payload);
    reply(rq, rs, 200, { stored: true });
  } catch (error) {
    next(error);
  }
});

app.get('/v1/data/:key', authAndDecrypt, async (rq, rs, next) => {
  try {
    const v = await kvGet(rq.params.key);
    if (v === null) return reply(rq, rs, 404, { error: 'not_found' });
    if (v === undefined) return reply(rq, rs, 409, { error: 'integrity_failure' });
    reply(rq, rs, 200, { value: v });
  } catch (error) {
    next(error);
  }
});

app.delete('/v1/data/:key', authAndDecrypt, async (rq, rs, next) => {
  try {
    await kvDelete(rq.params.key);
    reply(rq, rs, 200, { deleted: true });
  } catch (error) {
    next(error);
  }
});

// Centralized async error catcher to avoid raw 500 runtime execution crashes
app.use((errz, rq, rs, next) => {
  console.error('[RUNTIME ERROR]', errz);
  rs.status(500).json({ error: 'database_connectivity_failure', message: errz.message });
});

// ---------- bootstrap ----------
if (process.env.NODE_ENV !== 'production') {
  const PORT = process.env.PORT || 10000;
  app.listen(PORT, () => console.log(`Data server running locally on port ${PORT}`));
}

app.encryptField = encryptField;
app.decryptField = decryptField;
app.sessionKey = sessionKey;
module.exports = app;