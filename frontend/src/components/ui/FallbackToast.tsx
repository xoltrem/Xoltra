'use client';
import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { onFallbackUsed } from '@/lib/api';

export function FallbackToast() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    return onFallbackUsed(() => {
      setShow(true);
      setTimeout(() => setShow(false), 4000);
    });
  }, []);

  if (!show) return null;
  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[100] flex items-center gap-2 px-3 py-2 rounded-[var(--radius-global)] bg-[var(--color-panel-200)] border border-[var(--color-border-main)] text-xs text-[var(--color-text-primary)] shadow-xl">
      <RefreshCw className="w-3.5 h-3.5 animate-spin text-[var(--color-accent)]" />
      Reconnecting via backup server...
    </div>
  );
}
