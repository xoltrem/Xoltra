'use strict';
const router    = require('express').Router();
const axios     = require('axios');
const crypto    = require('crypto');
const nodemailer = require('nodemailer');
const { OAuth2Client } = require('google-auth-library');

const googleClient = new OAuth2Client(process.env.GOOGLE_CLIENT_ID);

// ─────────────────────────────────────────────
// OTP STORE  (in-memory — swap for Redis in prod)
// ─────────────────────────────────────────────
const otpStore = new Map(); // email → { otp, expiresAt, attempts }
const OTP_TTL  = 5 * 60 * 1000;  // 5 minutes
const MAX_ATTEMPTS = 5;

// ─────────────────────────────────────────────
// DISPOSABLE EMAIL BLOCKLIST
// ─────────────────────────────────────────────
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

// ─────────────────────────────────────────────
// EMAIL TRANSPORTER
// ─────────────────────────────────────────────
const transporter = nodemailer.createTransport({
  host:   process.env.SMTP_HOST,
  port:   Number(process.env.SMTP_PORT) || 587,
  secure: process.env.SMTP_SECURE === 'true',
  auth: {
    user: process.env.SMTP_USER,
    pass: process.env.SMTP_PASS,
  },
});

// ─────────────────────────────────────────────
// MIDDLEWARE 1 — Cloudflare Turnstile
// ─────────────────────────────────────────────
async function verifyTurnstile(req, res, next) {
  const token = req.body.turnstileToken;
  if (!token) return res.status(400).json({ error: 'Missing Turnstile token.' });

  try {
    const params = new URLSearchParams({
      secret:   process.env.TURNSTILE_SECRET_KEY,
      response: token,
      remoteip: req.ip,
    });
    const { data } = await axios.post(
      'https://challenges.cloudflare.com/turnstile/v0/siteverify',
      params.toString(),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    );
    if (!data.success) {
      return res.status(403).json({ error: 'Bot check failed. Please try again.' });
    }
    next();
  } catch (err) {
    console.error('[Turnstile]', err.message);
    return res.status(500).json({ error: 'Security check unavailable. Try again later.' });
  }
}

// ─────────────────────────────────────────────
// MIDDLEWARE 2 — Google token verification
// ─────────────────────────────────────────────
async function verifyGoogleToken(req, res, next) {
  const { accessToken } = req.body;
  if (!accessToken) return res.status(400).json({ error: 'Missing Google token.' });

  try {
    // getTokenInfo verifies the access token and returns user info
    const info = await googleClient.getTokenInfo(accessToken);
    if (!info.email || !info.email_verified) {
      return res.status(401).json({ error: 'Google account email not verified.' });
    }
    req.googleEmail = info.email.toLowerCase();
    req.googleSub   = info.sub;
    next();
  } catch (err) {
    console.error('[Google]', err.message);
    return res.status(401).json({ error: 'Invalid or expired Google token.' });
  }
}

// ─────────────────────────────────────────────
// MIDDLEWARE 3 — Block disposable emails
// ─────────────────────────────────────────────
function blockDisposableEmail(req, res, next) {
  const domain = req.googleEmail?.split('@')[1];
  if (!domain) return res.status(400).json({ error: 'Invalid email address.' });

  if (BLOCKLIST.has(domain)) {
    return res.status(403).json({
      error: 'Temporary or disposable email addresses are not permitted.',
    });
  }
  next();
}

// ─────────────────────────────────────────────
// OTP HELPERS
// ─────────────────────────────────────────────
function generateOTP(email) {
  // cryptographically random 6-digit number
  const otp = crypto.randomInt(100000, 999999).toString();
  otpStore.set(email, {
    otp,
    expiresAt: Date.now() + OTP_TTL,
    attempts:  0,
  });
  // auto-clean from memory after TTL
  setTimeout(() => otpStore.delete(email), OTP_TTL);
  return otp;
}

async function sendOTPEmail(email, otp) {
  const html = `
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:420px;margin:0 auto;padding:32px 24px;background:#0f0f0f;color:#e5e5e5;border-radius:12px">
      <p style="margin:0 0 8px;font-size:13px;color:#888;text-transform:uppercase;letter-spacing:.08em">Your login code</p>
      <div style="font-size:42px;font-weight:700;letter-spacing:12px;color:#fff;padding:20px 0;font-family:monospace">${otp}</div>
      <p style="margin:0;font-size:13px;color:#666">Expires in 5 minutes. Never share this code.</p>
    </div>`;

  await transporter.sendMail({
    from:    process.env.OTP_EMAIL_FROM,
    to:      email,
    subject: `${otp} — your login code`,
    text:    `Your login code is: ${otp}\n\nExpires in 5 minutes. Do not share this code.`,
    html,
  });
}

// ─────────────────────────────────────────────
// ROUTE: POST /api/auth/google
// Pipeline: Turnstile → Google → Disposable check → OTP
// ─────────────────────────────────────────────
router.post('/google',
  verifyTurnstile,
  verifyGoogleToken,
  blockDisposableEmail,
  async (req, res) => {
    try {
      const otp = generateOTP(req.googleEmail);
      await sendOTPEmail(req.googleEmail, otp);
      res.json({ email: req.googleEmail, message: 'OTP sent.' });
    } catch (err) {
      console.error('[OTP send]', err.message);
      res.status(500).json({ error: 'Failed to send verification email. Try again.' });
    }
  }
);

// ─────────────────────────────────────────────
// ROUTE: POST /api/auth/verify-otp
// ─────────────────────────────────────────────
router.post('/verify-otp', (req, res) => {
  const { email, otp } = req.body;
  if (!email || !otp) return res.status(400).json({ error: 'Email and OTP required.' });

  const normalizedEmail = email.toLowerCase();
  const record = otpStore.get(normalizedEmail);

  if (!record) {
    return res.status(400).json({ error: 'No pending verification for this email. Sign in again.' });
  }
  if (Date.now() > record.expiresAt) {
    otpStore.delete(normalizedEmail);
    return res.status(400).json({ error: 'Code expired. Sign in again to get a new one.' });
  }
  if (record.attempts >= MAX_ATTEMPTS) {
    otpStore.delete(normalizedEmail);
    return res.status(429).json({ error: 'Too many attempts. Sign in again.' });
  }

  record.attempts++;

  if (record.otp !== otp.toString()) {
    return res.status(400).json({ error: `Incorrect code. ${MAX_ATTEMPTS - record.attempts} attempt(s) remaining.` });
  }

  // ✓ verified — consume it
  otpStore.delete(normalizedEmail);

  // TODO: issue JWT / session here
  // e.g. const token = jwt.sign({ email: normalizedEmail }, process.env.JWT_SECRET, { expiresIn: '7d' });
  //      res.json({ success: true, token });

  res.json({ success: true, email: normalizedEmail });
});

module.exports = router;
