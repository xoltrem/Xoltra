'use client';
import { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2, Mail, Lock } from 'lucide-react';
import { register, login, setToken, setTermsConsent, joinOrg } from '@/lib/api';
import { startGoogleLogin, verifyOtp, getDeviceFingerprint } from '@/lib/authService';
import { TermsPreviewModal } from '@/components/auth/TermsPreviewModal';

/** Redeems an org invite code stashed by /join before sending someone here
 *  to log in or sign up first. Best-effort - a failed redemption shouldn't
 *  block the person from reaching the app. */
async function redeemPendingInvite() {
  try {
    const code = sessionStorage.getItem('xoltra_pending_invite');
    if (!code) return;
    sessionStorage.removeItem('xoltra_pending_invite');
    await joinOrg(code);
  } catch { /* invite may be invalid/expired - not fatal */ }
}

declare global {
  interface Window {
    google?: any;
    turnstile?: any;
    THREE?: any;
  }
}

type Mode = 'password' | 'google-otp';

/** WebGL animated dot-grid background, ported as-is from the reference
 *  design. Loads Three.js from a CDN script tag (no bundler import) so it
 *  stays a drop-in, self-contained visual with no new npm dependency. */
function DotGridBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let active = true;
    let renderer: any, geometry: any, material: any, scene: any, camera: any, animationId: number;

    const initThree = (THREE: any) => {
      if (!canvasRef.current || !active) return;
      const canvas = canvasRef.current;
      renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false });
      renderer.setPixelRatio(window.devicePixelRatio);
      renderer.setSize(window.innerWidth, window.innerHeight);

      scene = new THREE.Scene();
      camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

      const uniforms = {
        u_time: { value: 0 },
        u_resolution: { value: new THREE.Vector2(window.innerWidth * 2, window.innerHeight * 2) },
        u_opacities: { value: [0.3, 0.3, 0.3, 0.5, 0.5, 0.5, 0.8, 0.8, 0.8, 1.0] },
        u_colors: {
          value: [
            new THREE.Vector3(1, 1, 1), new THREE.Vector3(1, 1, 1), new THREE.Vector3(1, 1, 1),
            new THREE.Vector3(1, 1, 1), new THREE.Vector3(1, 1, 1), new THREE.Vector3(1, 1, 1),
          ],
        },
        u_total_size: { value: 20.0 },
        u_dot_size: { value: 6.0 },
        u_reverse: { value: 0 },
      };

      material = new THREE.ShaderMaterial({
        vertexShader: `
          precision mediump float;
          uniform vec2 u_resolution;
          out vec2 fragCoord;
          void main() {
            gl_Position = vec4(position, 1.0);
            fragCoord = (position.xy + 1.0) * 0.5 * u_resolution;
            fragCoord.y = u_resolution.y - fragCoord.y;
          }
        `,
        fragmentShader: `
          precision mediump float;
          in vec2 fragCoord;
          uniform float u_time;
          uniform float u_opacities[10];
          uniform vec3 u_colors[6];
          uniform float u_total_size;
          uniform float u_dot_size;
          uniform vec2 u_resolution;
          uniform int u_reverse;
          out vec4 fragColor;

          float PHI = 1.61803398874989484820459;
          float random(vec2 xy) {
              return fract(tan(distance(xy * PHI, xy) * 0.5) * xy.x);
          }

          void main() {
              vec2 st = fragCoord.xy;
              st.x -= abs(floor((mod(u_resolution.x, u_total_size) - u_dot_size) * 0.5));
              st.y -= abs(floor((mod(u_resolution.y, u_total_size) - u_dot_size) * 0.5));

              float opacity = step(0.0, st.x) * step(0.0, st.y);
              vec2 st2 = vec2(int(st.x / u_total_size), int(st.y / u_total_size));

              float frequency = 5.0;
              float show_offset = random(st2);
              float rand = random(st2 * floor((u_time / frequency) + show_offset + frequency));
              opacity *= u_opacities[int(rand * 10.0)];
              opacity *= 1.0 - step(u_dot_size / u_total_size, fract(st.x / u_total_size));
              opacity *= 1.0 - step(u_dot_size / u_total_size, fract(st.y / u_total_size));

              vec3 color = u_colors[int(show_offset * 6.0)];

              float animation_speed_factor = 3.0;
              vec2 center_grid = u_resolution / 2.0 / u_total_size;
              float dist_from_center = distance(center_grid, st2);
              float timing_offset_intro = dist_from_center * 0.01 + (random(st2) * 0.15);

              opacity *= step(timing_offset_intro, u_time * animation_speed_factor);
              opacity *= clamp((1.0 - step(timing_offset_intro + 0.1, u_time * animation_speed_factor)) * 1.25, 1.0, 1.25);

              fragColor = vec4(color, opacity);
              fragColor.rgb *= fragColor.a;
          }
        `,
        uniforms,
        glslVersion: THREE.GLSL3,
        blending: THREE.CustomBlending,
        blendSrc: THREE.SrcAlphaFactor,
        blendDst: THREE.OneFactor,
        transparent: true,
      });

      geometry = new THREE.PlaneGeometry(2, 2);
      scene.add(new THREE.Mesh(geometry, material));

      const startTime = performance.now();
      const animate = () => {
        if (!active) return;
        animationId = requestAnimationFrame(animate);
        uniforms.u_time.value = (performance.now() - startTime) / 1000.0;
        renderer.render(scene, camera);
      };
      animate();

      const handleResize = () => {
        renderer.setSize(window.innerWidth, window.innerHeight);
        uniforms.u_resolution.value.set(window.innerWidth * 2, window.innerHeight * 2);
      };
      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    };

    let cleanupResize: (() => void) | undefined;
    if (window.THREE) {
      cleanupResize = initThree(window.THREE);
    } else {
      const script = document.createElement('script');
      script.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js';
      script.async = true;
      script.onload = () => { if (window.THREE) cleanupResize = initThree(window.THREE); };
      document.head.appendChild(script);
    }

    return () => {
      active = false;
      cleanupResize?.();
      if (animationId) cancelAnimationFrame(animationId);
      renderer?.dispose();
      geometry?.dispose();
      material?.dispose();
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 z-0" />;
}

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
      theme: 'dark',
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
    if (tab === 'signup' && !agreed) {
      setError('Please agree to the Terms of Service and Privacy Policy first.');
      return;
    }
    if (!tokenClientRef.current) {
      setError('Google sign-in is still loading, try again in a moment.');
      return;
    }
    if (turnstileSiteKey && !turnstileTokenRef.current) {
      setError('Please complete the verification check below first.');
      return;
    }
    setError('');
    setLoading(true);
    tokenClientRef.current.requestAccessToken();
  }, [turnstileSiteKey, agreed, tab]);

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (tab === 'signup' && !agreed) {
      setError('Please agree to the Terms of Service and Privacy Policy first.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const result = tab === 'signup' ? await register(email, password, refCode) : await login(email, password);
      setToken(result.token);
      await redeemPendingInvite();
      try { await setTermsConsent('accepted'); } catch { /* full-screen gate will catch it */ }
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

  const inputClass =
    'w-full bg-black border border-[#333] rounded-md pl-9 pr-3 py-2.5 text-sm text-white placeholder:text-[#666] focus:outline-none focus:border-[#555] transition-colors';
  const socialBtnClass =
    'w-full flex items-center justify-center gap-2 text-sm font-medium px-3 py-2.5 rounded-md bg-white text-black disabled:opacity-40 hover:opacity-90 transition-opacity';

  return (
    <div className="relative w-full h-screen flex items-center justify-center overflow-y-auto no-scrollbar bg-black text-white">
      <DotGridBackground />
      <div
        className="absolute inset-0 z-[1] pointer-events-none"
        style={{ background: 'radial-gradient(circle at center, rgba(0,0,0,0.75) 0%, rgba(0,0,0,0) 100%)' }}
      />

      <div className="relative z-[2] w-full max-w-sm bg-[#121212] border border-[#222] rounded-xl p-8 shadow-2xl flex flex-col items-center">
        {/* Logo */}
        <img src="/xoltra-logo.png" alt="Xoltra" className="w-11 h-11 object-contain mb-3" />

        {mode === 'password' ? (
          <div className="w-full flex flex-col items-center text-center">
            <h1 className="text-xl font-semibold tracking-tight mb-1">
              {tab === 'signup' ? 'Create your Xoltra account' : 'Sign in to Xoltra'}
            </h1>
            <p className="text-sm text-[#888] mb-5">
              {tab === 'signup' ? 'Get started with Xoltra.' : 'Welcome back, sign in to continue.'}
            </p>

            <form onSubmit={handlePasswordSubmit} className="w-full flex flex-col gap-2.5">
              <div className="relative">
                <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#666]" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@work-email.com"
                  className={inputClass}
                />
              </div>
              <div className="relative">
                <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#666]" />
                <input
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password"
                  className={inputClass}
                />
              </div>

              {tab === 'signup' && (
                <label className="flex items-start gap-2 text-xs text-[#888] pt-1 text-left">
                  <input
                    type="checkbox"
                    checked={agreed}
                    onChange={(e) => setAgreed(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>
                    I agree to the{' '}
                    <button type="button" onClick={() => setLegalTab('tos')} className="text-white hover:underline">
                      Terms of Service
                    </button>{' '}
                    and{' '}
                    <button type="button" onClick={() => setLegalTab('privacy')} className="text-white hover:underline">
                      Privacy Policy
                    </button>
                  </span>
                </label>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 text-sm px-3 py-2.5 rounded-md bg-white text-black font-medium disabled:opacity-50 hover:opacity-90 transition-opacity mt-1"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                {tab === 'signup' ? 'Sign Up with Email' : 'Continue with Email'}
              </button>
            </form>

            {googleClientId && (
              <>
                <div className="h-px bg-[#222] w-full my-4" />
                {turnstileSiteKey && <div id="turnstile-container" className="mb-3 flex justify-center" />}
                <button onClick={handleGoogleClick} disabled={loading} className={socialBtnClass}>
                  <svg viewBox="0 0 24 24" className="w-[18px] h-[18px] shrink-0">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                  </svg>
                  {tab === 'signup' ? 'Sign up with Google' : 'Continue with Google'}
                </button>
              </>
            )}

            <div className="mt-5 text-sm text-[#888]">
              {tab === 'signup' ? 'Already have an account? ' : "Don't have an account? "}
              <button
                onClick={() => setTab(tab === 'signup' ? 'signin' : 'signup')}
                className="text-white font-medium hover:underline"
              >
                {tab === 'signup' ? 'Sign In' : 'Sign Up'}
              </button>
            </div>
          </div>
        ) : (
          <div className="w-full flex flex-col items-center text-center">
            <h1 className="text-xl font-semibold tracking-tight mb-1">Check your email</h1>
            <p className="text-sm text-[#888] mb-5">
              We sent a code to <span className="text-white">{pendingEmail}</span>.
            </p>
            <form onSubmit={handleOtpSubmit} className="w-full flex flex-col gap-2.5">
              <input
                type="text"
                required
                inputMode="numeric"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                placeholder="Enter code"
                className="w-full bg-black border border-[#333] rounded-md px-3 py-2.5 text-sm text-white placeholder:text-[#666] focus:outline-none focus:border-[#555] tracking-widest text-center transition-colors"
              />
              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 text-sm px-3 py-2.5 rounded-md bg-white text-black font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                Verify
              </button>
              <button
                type="button"
                onClick={() => { setMode('password'); setError(''); }}
                className="w-full text-xs text-[#888] hover:text-white transition-colors"
              >
                Back
              </button>
            </form>
          </div>
        )}

        {error && <p className="mt-4 text-xs text-red-400 text-center">{error}</p>}

        <div className="mt-5 text-xs text-[#666] leading-relaxed text-center">
          By proceeding, you agree to creating a Xoltra account
          <br />
          subject to our{' '}
          <button type="button" onClick={() => setLegalTab('tos')} className="text-[#999] hover:text-white hover:underline">
            Terms of Service
          </button>{' '}
          and{' '}
          <button type="button" onClick={() => setLegalTab('privacy')} className="text-[#999] hover:text-white hover:underline">
            Privacy Policy
          </button>
          .
        </div>
      </div>

      {legalTab && <TermsPreviewModal initialTab={legalTab} onClose={() => setLegalTab(null)} />}
    </div>
  );
}

export default function LoginPage() {
  // useSearchParams() (for ?ref=) requires a Suspense boundary in the App
  // Router, or `next build` fails outright.
  return (
    <Suspense fallback={null}>
      <LoginPageInner />
    </Suspense>
  );
}
