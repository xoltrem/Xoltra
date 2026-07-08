'use strict';
const router     = require('express').Router();
const axios      = require('axios');
const crypto     = require('crypto');
const nodemailer = require('nodemailer');
const { OAuth2Client } = require('google-auth-library');
const { Redis }  = require('@upstash/redis');

const googleClient = new OAuth2Client(process.env.GOOGLE_CLIENT_ID);
const redis = new Redis({
  url:   process.env.UPSTASH_REDIS_REST_URL,
  token: process.env.UPSTASH_REDIS_REST_TOKEN,
});

const OTP_TTL      = 300;  // seconds (5 min) — Redis native TTL
const MAX_ATTEMPTS = 5;

// ── disposable email blocklist ──
const BLOCKLIST = new Set([
  'mailinator.com','guerrillamail.com','guerrillamailblock.com','grr.la',
  'guerrillamail.info','guerrillamail.biz','guerrillamail.de','guerrillamail.net',
  'guerrillamail.org','tempmail.com','temp-mail.org','throwaway.email',
  'yopmail.com','yopmail.fr','cool.fr.nf','jetable.fr.nf','nospam.ze.tc',
  'nomail.xl.cx','mega.zik.dj','speed.1s.fr','courriel.fr.nf','moncourrier.fr.nf',
  '10minutemail.com','10minutemail.net','sharklasers.com','spam4.me',
  'trashmail.com','trashmail.me','trashmail.at','trashmail.io','trashmail.net',
  'fakeinbox.com','mailnull.com','maildrop.cc','dispostable.com',
  'spamgourmet.com','getairmail.com','filzmail.com','discard.email',
  'mailexpire.com','spambox.us','spamthis.co.uk','spamherelots.com',
  'tempr.email','tempemail.co','throwam.com','mt2015.com',
]);

// ── email transporter ──
const transporter = nodemailer.createTransport({
  host:   process.env.SMTP_HOST,
  port:   Number(process.env.SMTP_PORT) || 587,
  secure: process.env.SMTP_SECURE === 'true',
  auth:   { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS },
});

// ── middleware 1: Cloudflare Turnstile ──
async function verifyTurnstile(req, res, next) {
  const token = req.body.turnstileToken;
  if (!token) return res.status(400).json({ error: 'Missing Turnstile token.' });
  try {
    const { data } = await axios.post(
      'https://challenges.cloudflare.com/turnstile/v0/siteverify',
      new URLSearchParams({ secret: process.env.TURNSTILE_SECRET_KEY, response: token, remoteip: req.ip }).toString(),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    );
    if (!data.success) return res.status(403).json({ error: 'Bot check failed. Please try again.' });
    next();
  } catch {
    return res.status(500).json({ error: 'Security check unavailable. Try again later.' });
  }
}

// ── middleware 2: Google token ──
async function verifyGoogleToken(req, res, next) {
  const { accessToken } = req.body;
  if (!accessToken) return res.status(400).json({ error: 'Missing Google token.' });
  try {
    const info = await googleClient.getTokenInfo(accessToken);
    if (!info.email || !info.email_verified)
      return res.status(401).json({ error: 'Google account email not verified.' });
    req.googleEmail = info.email.toLowerCase();
    next();
  } catch {
    return res.status(401).json({ error: 'Invalid or expired Google token.' });
  }
}

// ── middleware 3: block disposable emails ──
function blockDisposableEmail(req, res, next) {
  const domain = req.googleEmail?.split('@')[1];
  if (!domain) return res.status(400).json({ error: 'Invalid email address.' });
  if (BLOCKLIST.has(domain))
    return res.status(403).json({ error: 'Temporary or disposable email addresses are not permitted.' });
  next();
}

// ── OTP helpers ──
async function generateOTP(email) {
  const otp = crypto.randomInt(100000, 999999).toString();
  await redis.set(`otp:${email}`, JSON.stringify({ otp, attempts: 0 }), { ex: OTP_TTL });
  return otp;
}

async function sendOTPEmail(email, otp) {
  const html = `
    <div style="font-family:-apple-system,sans-serif;max-width:420px;margin:0 auto;padding:32px 24px;background:#0f0f0f;color:#e5e5e5;border-radius:12px">
      <p style="margin:0 0 8px;font-size:13px;color:#888;text-transform:uppercase;letter-spacing:.08em">Your login code</p>
      <div style="font-size:42px;font-weight:700;letter-spacing:12px;color:#fff;padding:20px 0;font-family:monospace">${otp}</div>
      <p style="margin:0;font-size:13px;color:#666">Expires in 5 minutes. Never share this code.</p>
    </div>`;
  await transporter.sendMail({
    from:    process.env.OTP_EMAIL_FROM,
    to:      email,
    subject: `${otp} — your login code`,
    text:    `Your login code is: ${otp}\n\nExpires in 5 minutes. Do not share this.`,
    html,
  });
}

// ── POST /api/auth/google ──
router.post('/google',
  verifyTurnstile,
  verifyGoogleToken,
  blockDisposableEmail,
  async (req, res) => {
    try {
      const otp = await generateOTP(req.googleEmail);
      await sendOTPEmail(req.googleEmail, otp);
      res.json({ email: req.googleEmail, message: 'OTP sent.' });
    } catch (err) {
      console.error('[OTP send]', err.message);
      res.status(500).json({ error: 'Failed to send verification email. Try again.' });
    }
  }
);

// ── POST /api/auth/verify-otp ──
router.post('/verify-otp', async (req, res) => {
  const { email, otp } = req.body;
  if (!email || !otp) return res.status(400).json({ error: 'Email and OTP required.' });

  const key  = `otp:${email.toLowerCase()}`;
  const raw  = await redis.get(key);

  if (!raw) return res.status(400).json({ error: 'No pending verification. Sign in again.' });

  const record = typeof raw === 'string' ? JSON.parse(raw) : raw;

  if (record.attempts >= MAX_ATTEMPTS) {
    await redis.del(key);
    return res.status(429).json({ error: 'Too many attempts. Sign in again.' });
  }

  record.attempts++;

  if (record.otp !== otp.toString()) {
    await redis.set(key, JSON.stringify(record), { keepttl: true });
    return res.status(400).json({ error: `Incorrect code. ${MAX_ATTEMPTS - record.attempts} attempt(s) remaining.` });
  }

  await redis.del(key); // single-use — consume immediately
  // ── Flask handoff: OAuth just confirmed identity, but Flask (auth.py) is
  // the single source of truth for user records and JWTs. Every other
  // backend feature (personalization, subscription, workflows) only
  // understands Flask's JWT, so we mint one here instead of inventing a
  // second, incompatible token type.
  const FLASK_API_URL = process.env.FLASK_API_URL || 'http://localhost:5001';
  try {
    const { data } = await axios.post(`${FLASK_API_URL}/api/auth/oauth-issue`, {
      email: email.toLowerCase(),
      source: 'google_oauth',
    }, { timeout: 5000 });

    return res.json({
      success: true,
      email: email.toLowerCase(),
      token: data.token,   // real Flask JWT — works with every existing @require_auth route
      user: data.user,
    });
  } catch (err) {
    console.error('[auth.js] Flask handoff failed:', err.message);
    return res.status(502).json({
      error: 'Signed in with Google, but could not complete account setup. Try again.',
    });
  }
});

module.exports = router;
