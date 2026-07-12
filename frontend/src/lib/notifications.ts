const PREF_KEY = 'xoltra_notify_enabled';

export function notificationsEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  return localStorage.getItem(PREF_KEY) === 'true' && typeof Notification !== 'undefined' && Notification.permission === 'granted';
}

export async function enableNotifications(): Promise<boolean> {
  if (typeof window === 'undefined' || typeof Notification === 'undefined') return false;
  let permission = Notification.permission;
  if (permission === 'default') {
    permission = await Notification.requestPermission();
  }
  const granted = permission === 'granted';
  localStorage.setItem(PREF_KEY, granted ? 'true' : 'false');
  return granted;
}

export function disableNotifications() {
  localStorage.setItem(PREF_KEY, 'false');
}

export function notify(title: string, body?: string) {
  if (!notificationsEnabled()) return;
  try {
    new Notification(title, { body, icon: '/favicon.ico' });
  } catch {
    // Some browsers/contexts (e.g. no service worker on iOS) reject silently — non-fatal.
  }
}
