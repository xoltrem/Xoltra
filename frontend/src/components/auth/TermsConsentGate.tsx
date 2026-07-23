'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, ScrollText } from 'lucide-react';
import { usePathname } from 'next/navigation';
import { getTermsConsent, hasToken, setTermsConsent } from '@/lib/api';
import { useTermsStore } from '@/stores';
import { TERMS_OF_SERVICE_TEXT, PRIVACY_NOTICE_TEXT, POLICY_EFFECTIVE_DATE } from '@/lib/legalDocuments';

export function TermsConsentGate() {
  const pathname = usePathname();
  const { status, modalOpen, setStatus, setModalOpen } = useTermsStore();

  useEffect(() => {
    if (!hasToken()) {
      setStatus('unavailable');
      setModalOpen(false);
      return;
    }
    let cancelled = false;
    getTermsConsent()
      .then((result) => {
        if (cancelled) return;
        const next = result.terms.tos_status as 'pending' | 'accepted' | 'rejected';
        setStatus(next);
        setModalOpen(next === 'pending');
      })
      .catch(() => {
        if (!cancelled) setStatus('unavailable');
      });
    return () => { cancelled = true; };
  }, [pathname, setModalOpen, setStatus]);

  const saveDecision = useCallback(async (decision: 'accepted' | 'rejected') => {
    try {
      await setTermsConsent(decision);
      setStatus(decision);
      setModalOpen(false);
    } catch (e: unknown) {
      throw new Error(e instanceof Error ? e.message : 'Could not save your decision.');
    }
  }, [setModalOpen, setStatus]);

  if (!modalOpen || status === 'unavailable') return null;

  return <TermsDialog onDecision={saveDecision} />;
}

type Tab = 'tos' | 'privacy';

function TermsDialog({ onDecision }: { onDecision: (decision: 'accepted' | 'rejected') => Promise<void> }) {
  const [tab, setTab] = useState<Tab>('tos');
  const [viewedTos, setViewedTos] = useState(false);
  const [viewedPrivacy, setViewedPrivacy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const bothViewed = viewedTos && viewedPrivacy;

  const handleScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    if (target.scrollTop + target.clientHeight >= target.scrollHeight - 8) {
      if (tab === 'tos') setViewedTos(true);
      else setViewedPrivacy(true);
    }
  };

  const decide = async (decision: 'accepted' | 'rejected') => {
    setSaving(true);
    setError('');
    try {
      await onDecision(decision);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Could not save your decision.');
    } finally {
      setSaving(false);
    }
  };

  const text = tab === 'tos' ? TERMS_OF_SERVICE_TEXT : PRIVACY_NOTICE_TEXT;
  const currentViewed = tab === 'tos' ? viewedTos : viewedPrivacy;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4" role="dialog" aria-modal="true" aria-labelledby="terms-title">
      <div className="w-full max-w-3xl overflow-hidden rounded-[var(--radius-global)] border border-[var(--color-border-main)] bg-[var(--color-panel-100)] shadow-2xl">
        <div className="border-b border-[var(--color-border-main)] px-5 py-4">
          <div className="flex items-center gap-2 text-[var(--color-accent)]"><ScrollText className="h-4 w-4" /><span className="text-xs font-medium uppercase tracking-wider">Required before using Xoltra</span></div>
          <h2 id="terms-title" className="mt-1 text-lg font-semibold text-white">Terms of Service &amp; Privacy Notice</h2>
          <p className="mt-1 text-xs text-[var(--color-text-secondary)]">Effective {POLICY_EFFECTIVE_DATE}. Read both documents, then choose whether to accept them.</p>

          <div className="mt-3 flex gap-1 text-xs">
            <button
              type="button"
              onClick={() => setTab('tos')}
              className={`flex items-center gap-1.5 rounded-[var(--radius-global)] px-3 py-1.5 transition-colors ${tab === 'tos' ? 'bg-[var(--color-accent)]/10 text-[var(--color-accent)]' : 'text-[var(--color-text-secondary)] hover:text-white'}`}
            >
              Terms of Service {viewedTos && <span className="text-[var(--color-accent)]">✓</span>}
            </button>
            <button
              type="button"
              onClick={() => setTab('privacy')}
              className={`flex items-center gap-1.5 rounded-[var(--radius-global)] px-3 py-1.5 transition-colors ${tab === 'privacy' ? 'bg-[var(--color-accent)]/10 text-[var(--color-accent)]' : 'text-[var(--color-text-secondary)] hover:text-white'}`}
            >
              Privacy Notice {viewedPrivacy && <span className="text-[var(--color-accent)]">✓</span>}
            </button>
          </div>
        </div>

        <div
          key={tab}
          className="max-h-[52vh] overflow-y-auto p-5 whitespace-pre-wrap text-xs leading-relaxed text-[var(--color-text-secondary)]"
          onScroll={handleScroll}
        >
          {text}
          <div className="h-1" aria-hidden="true" />
        </div>

        <div className="border-t border-[var(--color-border-main)] px-5 py-4">
          {!currentViewed && (
            <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
              Scroll to the bottom of {tab === 'tos' ? 'the Terms of Service' : 'the Privacy Notice'} to mark it as read.
            </p>
          )}
          {currentViewed && !bothViewed && (
            <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
              Now read the {tab === 'tos' ? 'Privacy Notice' : 'Terms of Service'} tab above before you can continue.
            </p>
          )}
          {error && <p className="mb-3 text-xs text-red-400">{error}</p>}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button type="button" disabled={!bothViewed || saving} onClick={() => decide('rejected')} className="rounded-[var(--radius-global)] border border-[var(--color-border-main)] px-4 py-2 text-xs text-[var(--color-text-secondary)] transition-colors hover:text-white disabled:cursor-not-allowed disabled:opacity-40">
              Decline
            </button>
            <button type="button" disabled={!bothViewed || saving} onClick={() => decide('accepted')} className="flex items-center justify-center gap-2 rounded-[var(--radius-global)] bg-[var(--color-accent)] px-4 py-2 text-xs font-medium text-black transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40">
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Accept Both
            </button>
          </div>
          {bothViewed && (
            <p className="mt-2 text-[10px] text-[var(--color-text-secondary)]">
              Declining blocks account access until you accept — this isn't a limited-access mode.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
