'use client';
import { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2, Mail, Lock } from 'lucide-react';
import { register, login, setToken, setTermsConsent, joinOrg } from '@/lib/api';
import { startGoogleLogin, verifyOtp, getDeviceFingerprint } from '@/lib/authService';
import { TermsPreviewModal } from '@/components/auth/TermsPreviewModal';

/** Redeems an org invite code stashed by /join before sending someone here
 *  to log in or sign up first. Best-effort — a failed redemption shouldn't
 *  block the person from reaching the app. */
async function redeemPendingInvite() {
  try {
    const code = sessionStorage.getItem('xoltra_pending_invite');
    if (!code) return;
    sessionStorage.removeItem('xoltra_pending_invite');
    await joinOrg(code);
  } catch { /* invite may be invalid/expired — not fatal */ }
}

declare global {
  interface Window {
    google?: any;
    turnstile?: any;
  }
}

type Mode = 'password' | 'google-otp';

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const refCode = searchParams.get('ref') || undefined;
  const [tab, setTab] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [mode, setMode] = useState<Mode>('password');
  const [pendingEmail, setPendingEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [googleReady, setGoogleReady] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [legalTab, setLegalTab] = useState<'tos' | 'privacy' | null>(null);

  const turnstileWidgetId = useRef<string | null>(null);
  const turnstileTokenRef = useRef<string>('');
  const tokenClientRef = useRef<any>(null);

  const googleClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  const turnstileSiteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;

  // Load Google Identity Services + Turnstile scripts once, scoped to this
  // page only (the rest of the app never needs them).
  useEffect(() => {
    const loadScript = (src: string, id: string) =>
      new Promise<void>((resolve) => {
        if (document.getElementById(id)) return resolve();
        const s = document.createElement('script');
        s.src = src;
        s.id = id;
        s.async = true;
        s.onload = () => resolve();
        document.head.appendChild(s);
      });

    Promise.all([
      loadScript('https://accounts.google.com/gsi/client', 'gsi-script'),
      loadScript('https://challenges.cloudflare.com/turnstile/v0/api.js', 'turnstile-script'),
    ]).then(() => setGoogleReady(true));
  }, []);

  useEffect(() => {
    if (!googleReady || !window.turnstile || turnstileWidgetId.current || !turnstileSiteKey) return;
    turnstileWidgetId.current = window.turnstile.render('#turnstile-container', {
      sitekey: turnstileSiteKey,
      callback: (token: string) => { turnstileTokenRef.current = token; },
    });
  }, [googleReady, turnstileSiteKey]);

  useEffect(() => {
    if (!googleReady || !window.google || !googleClientId) return;
    tokenClientRef.current = window.google.accounts.oauth2.initTokenClient({
      client_id: googleClientId,
      scope: 'email profile',
      callback: async (resp: any) => {
        if (!resp.access_token) {
          setError('Google sign-in was cancelled or failed.');
          setLoading(false);
          return;
        }
        try {
          const fingerprint = getDeviceFingerprint();
          const result = await startGoogleLogin(resp.access_token, turnstileTokenRef.current, fingerprint, refCode);
          setPendingEmail(result.email);
          setMode('google-otp');
        } catch (e: any) {
          setError(e.message || 'Google sign-in failed.');
        } finally {
          setLoading(false);
        }
      },
    });
  }, [googleReady, googleClientId]);

  const handleGoogleClick = useCallback(() => {
    if (!agreed) {
      setError('Please agree to the Terms of Service and Privacy Notice first.');
      return;
    }
    if (!tokenClientRef.current) {
      setError('Google sign-in is still loading — try again in a moment.');
      return;
    }
    if (turnstileSiteKey && !turnstileTokenRef.current) {
      setError('Please complete the verification check below first.');
      return;
    }
    setError('');
    setLoading(true);
    tokenClientRef.current.requestAccessToken();
  }, [turnstileSiteKey, agreed]);

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agreed) {
      setError('Please agree to the Terms of Service and Privacy Notice first.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const result = tab === 'signup' ? await register(email, password, refCode) : await login(email, password);
      setToken(result.token);
      await redeemPendingInvite();
      // The checkbox above already required explicit agreement before this
      // form could even submit — record that now so the full-screen ToS
      // gate on the next page doesn't immediately re-block them with the
      // same question. Best-effort: if this fails, the gate is still the
      // real enforcement point and will just ask again.
      try { await setTermsConsent('accepted'); } catch { /* gate will catch it */ }
      router.push('/pricing');
    } catch (e: any) {
      setError(e.message || 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  const handleOtpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result = await verifyOtp(pendingEmail, otp);
      setToken(result.token);
      await redeemPendingInvite();
      try { await setTermsConsent('accepted'); } catch { /* gate will catch it */ }
      router.push('/pricing');
    } catch (e: any) {
      setError(e.message || 'Invalid or expired code.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-full flex items-center justify-center p-6">
      <div className="w-full max-w-sm bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-6">
        <h1 className="text-lg font-medium text-[var(--color-text-primary)] mb-1">
          {mode === 'google-otp' ? 'Check your email' : 'Sign in to Xoltra'}
        </h1>

        {mode === 'password' && (
          <>
            <div className="flex gap-4 mb-4 text-xs">
              <button
                onClick={() => setTab('signin')}
                className={tab === 'signin' ? 'text-[var(--color-accent)] font-medium' : 'text-[var(--color-text-secondary)]'}
              >
                Sign in
              </button>
              <button
                onClick={() => setTab('signup')}
                className={tab === 'signup' ? 'text-[var(--color-accent)] font-medium' : 'text-[var(--color-text-secondary)]'}
              >
                Create account
              </button>
            </div>

            <form onSubmit={handlePasswordSubmit} className="space-y-3">
              <div className="relative">
                <Mail className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-secondary)]" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] pl-9 pr-3 py-2 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-accent)]/40"
                />
              </div>
              <div className="relative">
                <Lock className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-secondary)]" />
                <input
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password"
                  className="w-full bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] pl-9 pr-3 py-2 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-accent)]/40"
                />
              </div>
              <label className="flex items-start gap-2 text-[11px] text-[var(--color-text-secondary)] pt-1">
                <input
                  type="checkbox"
                  checked={agreed}
                  onChange={(e) => setAgreed(e.target.checked)}
                  className="mt-0.5"
                />
                <span>
                  I agree to the{' '}
                  <button type="button" onClick={() => setLegalTab('tos')} className="text-[var(--color-accent)] hover:underline">
                    Terms of Service
                  </button>{' '}
                  and{' '}
                  <button type="button" onClick={() => setLegalTab('privacy')} className="text-[var(--color-accent)] hover:underline">
                    Privacy Notice
                  </button>
                </span>
              </label>
              <button
                type="submit"
                disabled={loading || !agreed}
                className="w-full flex items-center justify-center gap-2 text-xs px-3 py-2 rounded-[var(--radius-global)] bg-[var(--color-accent)] text-black font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
              >
                {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {tab === 'signup' ? 'Create account' : 'Sign in'}
              </button>
            </form>

            {googleClientId && (
              <>
                <div className="flex items-center gap-2 my-4">
                  <div className="flex-1 h-px bg-[var(--color-border-main)]" />
                  <span className="text-[10px] text-[var(--color-text-secondary)]">or</span>
                  <div className="flex-1 h-px bg-[var(--color-border-main)]" />
                </div>

                {turnstileSiteKey && <div id="turnstile-container" className="mb-3 flex justify-center" />}

                <button
                  onClick={handleGoogleClick}
                  disabled={loading || !googleReady || !agreed}
                  className="w-full flex items-center justify-center gap-2 text-xs px-3 py-2 rounded-[var(--radius-global)] border border-[var(--color-border-main)] text-[var(--color-text-primary)] disabled:opacity-50 hover:bg-[var(--color-panel-200)] transition-colors"
                >
                  Continue with Google
                </button>
              </>
            )}
          </>
        )}

        {mode === 'google-otp' && (
          <form onSubmit={handleOtpSubmit} className="space-y-3">
            <p className="text-xs text-[var(--color-text-secondary)]">
              We sent a code to <span className="text-[var(--color-text-primary)]">{pendingEmail}</span>.
            </p>
            <input
              type="text"
              required
              inputMode="numeric"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              placeholder="Enter code"
              className="w-full bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-accent)]/40 tracking-widest text-center"
            />
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 text-xs px-3 py-2 rounded-[var(--radius-global)] bg-[var(--color-accent)] text-black font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
            >
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Verify
            </button>
            <button
              type="button"
              onClick={() => { setMode('password'); setError(''); }}
              className="w-full text-[10px] text-[var(--color-text-secondary)] hover:text-white transition-colors"
            >
              Back
            </button>
          </form>
        )}

        {error && <p className="mt-3 text-[11px] text-red-400">{error}</p>}
      </div>

      {legalTab && <TermsPreviewModal initialTab={legalTab} onClose={() => setLegalTab(null)} />}
    </div>
  );
}

export default function LoginPage() {
  // useSearchParams() (for ?ref=) requires a Suspense boundary in the App
  // Router, or `next build` fails outright, same class of build-strictness
  // issue as the Tailwind devDependencies fix, not optional to skip.
  return (
    <Suspense fallback={null}>
      <LoginPageInner />
    </Suspense>
  );
}
