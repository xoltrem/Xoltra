'use client';

import { useState } from 'react';
import { ScrollText, X } from 'lucide-react';
import { TERMS_OF_SERVICE_TEXT, PRIVACY_NOTICE_TEXT, POLICY_EFFECTIVE_DATE } from '@/lib/legalDocuments';

type Tab = 'tos' | 'privacy';

export function TermsPreviewModal({ initialTab = 'tos', onClose }: { initialTab?: Tab; onClose: () => void }) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const text = tab === 'tos' ? TERMS_OF_SERVICE_TEXT : PRIVACY_NOTICE_TEXT;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-3xl overflow-hidden rounded-[var(--radius-global)] border border-[var(--color-border-main)] bg-[var(--color-panel-100)] shadow-2xl">
        <div className="flex items-start justify-between border-b border-[var(--color-border-main)] px-5 py-4">
          <div>
            <div className="flex items-center gap-2 text-[var(--color-accent)]">
              <ScrollText className="h-4 w-4" />
              <span className="text-xs font-medium uppercase tracking-wider">Xoltra Legal</span>
            </div>
            <h2 className="mt-1 text-lg font-semibold text-white">Terms of Service &amp; Privacy Notice</h2>
            <p className="mt-1 text-xs text-[var(--color-text-secondary)]">Effective {POLICY_EFFECTIVE_DATE}.</p>
          </div>
          <button type="button" onClick={onClose} className="text-[var(--color-text-secondary)] hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-3 flex gap-1 px-5 text-xs">
          <button
            type="button"
            onClick={() => setTab('tos')}
            className={`rounded-[var(--radius-global)] px-3 py-1.5 transition-colors ${tab === 'tos' ? 'bg-[var(--color-accent)]/10 text-[var(--color-accent)]' : 'text-[var(--color-text-secondary)] hover:text-white'}`}
          >
            Terms of Service
          </button>
          <button
            type="button"
            onClick={() => setTab('privacy')}
            className={`rounded-[var(--radius-global)] px-3 py-1.5 transition-colors ${tab === 'privacy' ? 'bg-[var(--color-accent)]/10 text-[var(--color-accent)]' : 'text-[var(--color-text-secondary)] hover:text-white'}`}
          >
            Privacy Notice
          </button>
        </div>

        <div className="max-h-[52vh] overflow-y-auto p-5 mt-2 whitespace-pre-wrap text-xs leading-relaxed text-[var(--color-text-secondary)]">
          {text}
        </div>

        <div className="border-t border-[var(--color-border-main)] px-5 py-3 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-[var(--radius-global)] bg-[var(--color-accent)] px-4 py-2 text-xs font-medium text-black transition-opacity hover:opacity-90"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
