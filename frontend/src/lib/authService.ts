/**
 * authService.ts
 *
 * Talks to the separate Node auth-service (Google OAuth + email OTP +
 * Turnstile + rate limiting + device fingerprinting), NOT the Flask
 * backend — different base URL, different auth model (no Bearer token
 * yet, that's what this flow produces).
 */

const AUTH_SERVICE_URL = process.env.NEXT_PUBLIC_AUTH_SERVICE_URL || 'http://localhost:5000';

async function post(path: string, body: object) {
  const res = await fetch(`${AUTH_SERVICE_URL}/api/auth${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

/** Step 1: Google access token + Turnstile token -> sends an OTP email. */
export const startGoogleLogin = (accessToken: string, turnstileToken: string, fingerprint: string) =>
  post('/google', { accessToken, turnstileToken, fingerprint });

/** Step 2: the code from that email -> a real Flask JWT, ready for xoltra_token. */
export const verifyOtp = (email: string, otp: string) =>
  post('/verify-otp', { email, otp });

/**
 * Layer 4 fraud signal (see planning doc): a hash of stable browser
 * characteristics, not a hardware identifier. Good enough to notice "the
 * same device creating many accounts in a row" — nothing more invasive.
 */
export function getDeviceFingerprint(): string {
  const raw = [
    navigator.userAgent,
    navigator.language,
    `${screen.width}x${screen.height}x${screen.colorDepth}`,
    Intl.DateTimeFormat().resolvedOptions().timeZone,
    String(navigator.hardwareConcurrency || ''),
  ].join('|');

  // Small, dependency-free string hash — this is a fraud-detection signal,
  // not a security boundary, so cryptographic strength isn't the goal here.
  let hash = 0;
  for (let i = 0; i < raw.length; i++) {
    hash = (hash << 5) - hash + raw.charCodeAt(i);
    hash |= 0;
  }
  return `fp_${Math.abs(hash)}`;
}
