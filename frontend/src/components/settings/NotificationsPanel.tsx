'use client';
import { useEffect, useState } from 'react';
import { Bell } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { notificationsEnabled, enableNotifications, disableNotifications } from '@/lib/notifications';

export function NotificationsPanel() {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => { setEnabled(notificationsEnabled()); }, []);

  const toggle = async () => {
    if (enabled) { disableNotifications(); setEnabled(false); return; }
    setEnabled(await enableNotifications());
  };

  return (
    <div>
      <h2 className="text-xl font-semibold tracking-tight mb-1">Notifications</h2>
      <p className="text-sm text-[var(--color-text-secondary)] mb-4">
        Get a desktop notification when Xoltra finishes responding.
      </p>
      <div className="flex items-center justify-between p-3 border border-[var(--color-border-main)] rounded-[var(--radius-global)]">
        <div className="flex items-center gap-2 text-sm">
          <Bell className="w-4 h-4 text-[var(--color-text-secondary)]" />
          Desktop notifications
        </div>
        <Button size="sm" variant={enabled ? 'default' : 'outline'} onClick={toggle}>
          {enabled ? 'Enabled' : 'Enable'}
        </Button>
      </div>
    </div>
  );
}
