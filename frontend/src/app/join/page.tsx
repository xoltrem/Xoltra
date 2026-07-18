'use client';
import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2, Users } from 'lucide-react';
import { joinOrg, hasToken } from '@/lib/api';

function JoinPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const code = searchParams.get('code');
  const [status, setStatus] = useState<'checking' | 'joining' | 'error'>('checking');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!code) {
      setStatus('error');
      setError('This invite link is missing its code.');
      return;
    }

    if (!hasToken()) {
      // Not logged in, stash the code, send them to sign up/log in first,
      // login page redeems it right after auth succeeds.
      sessionStorage.setItem('xoltra_pending_invite', code);
      router.push('/login');
      return;
    }

    setStatus('joining');
    joinOrg(code)
      .then(() => router.push('/workflows'))
      .catch((e: any) => {
        setStatus('error');
        setError(e.message || 'This invite is invalid or has expired.');
      });
  }, [code]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-main)]">
      <div className="text-center space-y-3">
        <Users className="w-6 h-6 text-[var(--color-accent)] mx-auto" />
        {status !== 'error' ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin mx-auto text-[var(--color-text-secondary)]" />
            <p className="text-sm text-[var(--color-text-secondary)]">Joining the team...</p>
          </>
        ) : (
          <p className="text-sm text-[var(--color-error)] max-w-xs">{error}</p>
        )}
      </div>
    </div>
  );
}

export default function JoinPage() {
  return (
    <Suspense fallback={null}>
      <JoinPageInner />
    </Suspense>
  );
}
