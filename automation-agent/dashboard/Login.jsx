import { useState, useRef } from 'react';
import { useGoogleLogin } from '@react-oauth/google';
import { Turnstile } from '@marsidev/react-turnstile';
import axios from 'axios';

const API = import.meta.env.VITE_API_URL || 'http://localhost:5000';

export default function Login() {
  const [step, setStep]           = useState('login'); // 'login' | 'otp' | 'success'
  const [tsToken, setTsToken]     = useState(null);
  const [userEmail, setUserEmail] = useState('');
  const [otp, setOtp]             = useState(Array(6).fill(''));
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');
  const otpRefs                   = useRef([]);

  // ── Google login → send both tokens to backend ──
  const googleLogin = useGoogleLogin({
    onSuccess: async ({ access_token }) => {
      if (!tsToken) { setError('Complete the security check first.'); return; }
      setLoading(true); setError('');
      try {
        const { data } = await axios.post(`${API}/api/auth/google`, {
          accessToken:    access_token,
          turnstileToken: tsToken,
        });
        setUserEmail(data.email);
        setStep('otp');
      } catch (e) {
        setError(e.response?.data?.error || 'Authentication failed.');
      } finally { setLoading(false); }
    },
    onError: () => setError('Google sign-in was cancelled or failed.'),
  });

  // ── OTP input handlers ──
  const handleOtpChange = (val, idx) => {
    if (!/^\d*$/.test(val)) return;
    const next = [...otp];
    next[idx] = val.slice(-1);
    setOtp(next);
    if (val && idx < 5) otpRefs.current[idx + 1]?.focus();
  };

  const handleOtpKey = (e, idx) => {
    if (e.key === 'Backspace' && !otp[idx] && idx > 0)
      otpRefs.current[idx - 1]?.focus();
    if (e.key === 'Enter') submitOtp();
  };

  const handleOtpPaste = (e) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (pasted.length === 6) {
      setOtp(pasted.split(''));
      otpRefs.current[5]?.focus();
    }
  };

  // ── submit OTP ──
  const submitOtp = async () => {
    const code = otp.join('');
    if (code.length < 6) { setError('Enter all 6 digits.'); return; }
    setLoading(true); setError('');
    try {
      await axios.post(`${API}/api/auth/verify-otp`, { email: userEmail, otp: code });
      setStep('success');
    } catch (e) {
      setError(e.response?.data?.error || 'Invalid or expired code.');
      setOtp(Array(6).fill(''));
      otpRefs.current[0]?.focus();
    } finally { setLoading(false); }
  };

  const restart = () => { setStep('login'); setTsToken(null); setOtp(Array(6).fill('')); setError(''); };

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">

        {/* ── STEP 1: Login ── */}
        {step === 'login' && (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-2xl">
            <div className="text-center mb-8">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 mb-4">
                <svg className="w-6 h-6 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"/>
                </svg>
              </div>
              <h1 className="text-xl font-semibold text-white mb-1">Secure Sign In</h1>
              <p className="text-gray-500 text-sm">Complete the check below, then continue with Google.</p>
            </div>

            {/* Turnstile */}
            <div className="flex justify-center mb-5">
              <Turnstile
                siteKey={import.meta.env.VITE_TURNSTILE_SITE_KEY}
                onSuccess={token => { setTsToken(token); setError(''); }}
                onExpire={() => setTsToken(null)}
                onError={() => setError('Security check failed — refresh and try again.')}
                options={{ theme: 'dark' }}
              />
            </div>

            {/* Google Button */}
            <button
              onClick={() => { setError(''); googleLogin(); }}
              disabled={!tsToken || loading}
              className="w-full flex items-center justify-center gap-3 bg-white hover:bg-gray-100 active:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed text-gray-800 font-medium py-3 px-4 rounded-xl transition-all duration-150 text-sm shadow-sm"
            >
              <GoogleIcon />
              {loading ? 'Verifying…' : 'Continue with Google'}
            </button>

            {!tsToken && (
              <p className="text-center text-gray-600 text-xs mt-3">Complete the security check to enable sign-in.</p>
            )}

            {error && <ErrorMsg text={error} />}
          </div>
        )}

        {/* ── STEP 2: OTP ── */}
        {step === 'otp' && (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-2xl">
            <div className="text-center mb-8">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 mb-4">
                <svg className="w-6 h-6 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75"/>
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-white mb-1">Check your email</h2>
              <p className="text-gray-500 text-sm">
                We sent a 6-digit code to
                <span className="block text-gray-300 font-medium mt-0.5">{userEmail}</span>
              </p>
            </div>

            {/* 6-digit OTP inputs */}
            <div className="flex gap-2 justify-center mb-6" onPaste={handleOtpPaste}>
              {otp.map((digit, i) => (
                <input
                  key={i}
                  ref={el => otpRefs.current[i] = el}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  autoFocus={i === 0}
                  onChange={e => handleOtpChange(e.target.value, i)}
                  onKeyDown={e => handleOtpKey(e, i)}
                  className="w-11 h-13 text-center text-lg font-bold bg-gray-800 border-2 border-gray-700 focus:border-indigo-500 focus:outline-none text-white rounded-xl transition-colors caret-transparent"
                  style={{ height: '52px' }}
                />
              ))}
            </div>

            <button
              onClick={submitOtp}
              disabled={loading || otp.join('').length < 6}
              className="w-full bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium py-3 rounded-xl transition-colors text-sm"
            >
              {loading ? 'Verifying…' : 'Verify Code'}
            </button>

            <p className="text-gray-600 text-xs text-center mt-4">
              Code expires in 5 minutes.{' '}
              <button onClick={restart} className="text-indigo-400 hover:text-indigo-300 hover:underline transition-colors">
                Start over
              </button>
            </p>

            {error && <ErrorMsg text={error} />}
          </div>
        )}

        {/* ── STEP 3: Success ── */}
        {step === 'success' && (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-2xl text-center">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-green-500/10 border border-green-500/20 mb-5">
              <svg className="w-7 h-7 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7"/>
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-white mb-2">Access granted</h2>
            <p className="text-gray-500 text-sm">You're authenticated as<br/>
              <span className="text-gray-300 font-medium">{userEmail}</span>
            </p>
          </div>
        )}

      </div>
    </div>
  );
}

function ErrorMsg({ text }) {
  return (
    <div className="mt-4 flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5">
      <svg className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/>
      </svg>
      <p className="text-red-400 text-sm">{text}</p>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 24 24">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  );
}
