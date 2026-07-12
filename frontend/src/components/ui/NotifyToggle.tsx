'use client';
import { useEffect, useState } from 'react';
import { Bell, BellOff } from 'lucide-react';
import { notificationsEnabled, enableNotifications, disableNotifications } from '@/lib/notifications';

export function NotifyToggle() {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => { setEnabled(notificationsEnabled()); }, []);

  const toggle = async () => {
    if (enabled) {
      disableNotifications();
      setEnabled(false);
      return;
    }
    const granted = await enableNotifications();
    setEnabled(granted);
    if (!granted) alert('Desktop notifications were blocked. Enable them in your browser settings to use this.');
  };

  return (
    <button
      onClick={toggle}
      title={enabled ? 'Desktop notifications on — click to turn off' : 'Notify me when Xoltra responds'}
      className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-global)] text-[var(--color-text-secondary)] hover:text-white hover:bg-[var(--color-panel-200)] transition-colors"
    >
      {enabled ? <Bell className="w-4 h-4 text-[var(--color-accent)]" /> : <BellOff className="w-4 h-4" />}
    </button>
  );
}
