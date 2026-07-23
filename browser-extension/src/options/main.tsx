/**
 * options/main.tsx — sign-in and connection settings.
 *
 * Auth: email/password -> POST /api/auth/login -> JWT stored in
 * chrome.storage.local. The JWT expires after 24h (no refresh token exists
 * server-side), so the panel routes users back here on 401.
 *
 * Custom backend URLs beyond the localhost defaults need a host permission
 * grant — requested here interactively via chrome.permissions.request, never
 * broadly at install.
 */
import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { friendlyError, getMe, login } from '../shared/api';
import { getSettings, getToken, setSettings, setToken } from '../shared/storage';
import { DEFAULT_SETTINGS, type Settings } from '../shared/types';

function originPattern(url: string): string | null {
  try {
    return `${new URL(url).origin}/*`;
  } catch {
    return null;
  }
}

function Options() {
  const [settings, setSettingsState] = useState<Settings>(DEFAULT_SETTINGS);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [signedInAs, setSignedInAs] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  useEffect(() => {
    void getSettings().then(setSettingsState);
    void getToken().then(t => {
      if (!t) return;
      getMe()
        .then(r => {
          const user = (r as { user?: { email?: string } }).user;
          setSignedInAs(user?.email ?? 'signed in');
        })
        .catch(() => setSignedInAs('token saved (could not verify — backend offline?)'));
    });
  }, []);

  const ensureHostPermission = async (url: string): Promise<boolean> => {
    const pattern = originPattern(url);
    if (!pattern) return false;
    if (await chrome.permissions.contains({ origins: [pattern] })) return true;
    return chrome.permissions.request({ origins: [pattern] });
  };

  const saveSettings = async () => {
    setBusy(true);
    setMsg(null);
    try {
      for (const url of [settings.primaryUrl, settings.fallbackUrl]) {
        if (url && !(await ensureHostPermission(url))) {
          setMsg({ kind: 'err', text: `Permission for ${url} was not granted — requests to it will fail.` });
        }
      }
      await setSettings(settings);
      setMsg(m => m ?? { kind: 'ok', text: 'Settings saved.' });
    } finally {
      setBusy(false);
    }
  };

  const signIn = async () => {
    if (!email.trim() || !password) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await login(email.trim(), password);
      const token = r.token || r.access_token;
      if (!token) throw new Error('Login succeeded but no token was returned');
      await setToken(String(token));
      setSignedInAs(email.trim());
      setPassword('');
      setMsg({ kind: 'ok', text: 'Signed in — the side panel is ready.' });
    } catch (e: unknown) {
      setMsg({ kind: 'err', text: friendlyError(e) });
    } finally {
      setBusy(false);
    }
  };

  const signOut = async () => {
    await setToken(null);
    setSignedInAs(null);
    setMsg({ kind: 'ok', text: 'Signed out.' });
  };

  return (
    <div className="options">
      <h1>Xoltra Companion</h1>

      <section className="card">
        <h2>Account</h2>
        {signedInAs ? (
          <div className="row spread">
            <span className="small">Signed in as <strong>{signedInAs}</strong></span>
            <button className="btn" onClick={signOut} disabled={busy}>Sign out</button>
          </div>
        ) : (
          <>
            <label><span>Email</span>
              <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="username" />
            </label>
            <label><span>Password</span>
              <input
                className="input"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') void signIn(); }}
                autoComplete="current-password"
              />
            </label>
            <button className="btn btn-primary" onClick={signIn} disabled={busy || !email.trim() || !password}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
            <p className="tiny muted">
              Uses your Xoltra account. Sessions last 24 hours; you&apos;ll be asked to sign in again after that.
              Terms of Service are accepted in the web app, not here.
            </p>
          </>
        )}
      </section>

      <section className="card">
        <h2>Connection</h2>
        <label><span>Backend URL</span>
          <input className="input mono" value={settings.primaryUrl} onChange={e => setSettingsState(s => ({ ...s, primaryUrl: e.target.value }))} />
        </label>
        <label><span>Fallback backend URL</span>
          <input className="input mono" value={settings.fallbackUrl} onChange={e => setSettingsState(s => ({ ...s, fallbackUrl: e.target.value }))} />
        </label>
        <label><span>Web app URL (for &quot;Edit&quot; links)</span>
          <input className="input mono" value={settings.webAppUrl} onChange={e => setSettingsState(s => ({ ...s, webAppUrl: e.target.value }))} />
        </label>
        <button className="btn" onClick={saveSettings} disabled={busy}>Save connection settings</button>
        <p className="tiny muted">
          Non-localhost URLs prompt for a one-time site permission — the extension only ever
          gets access to origins you explicitly approve.
        </p>
      </section>

      {msg && (
        <div className={msg.kind === 'err' ? 'error-box' : 'card'} style={msg.kind === 'ok' ? { padding: '8px 10px', fontSize: 12, color: 'var(--color-success)' } : undefined}>
          {msg.text}
        </div>
      )}
    </div>
  );
}

const rootEl = document.getElementById('root');
if (rootEl) createRoot(rootEl).render(<Options />);
