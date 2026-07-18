'use client';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/Button';

// Public landing page. No sidebar/topbar (see layout.tsx) — this is the
// only page a signed-out visitor sees before choosing to sign in/up.
// Flow: Welcome ("/") -> Login/Signup ("/login") -> Pricing ("/pricing").
export default function WelcomePage() {
  const router = useRouter();

  return (
    <div className="h-screen w-full overflow-y-auto bg-[var(--color-bg-main)] text-[var(--color-text-primary)]">
      <section className="h-screen w-full flex items-center justify-center">
        <h1 className="text-3xl font-semibold">Welcome to</h1>
      </section>

      <section className="h-screen w-full flex flex-col items-center justify-center gap-6">
        <h2 className="text-5xl font-bold tracking-tight">Xoltra</h2>
        <Button size="lg" onClick={() => router.push('/login')}>
          Sign In / Sign Up
        </Button>
      </section>
    </div>
  );
}
