'use client';
import React from 'react';
import { useRouter } from 'next/navigation';
import { useScroll, useTransform } from 'framer-motion';
import { Button } from '@/components/ui/Button';
import { GoogleGeminiEffect } from '@/components/ui/google-gemini-effect';
import { CommitsGrid } from '@/components/ui/commits-grid';

// Public landing page. No sidebar/topbar (see layout.tsx) — this is the
// only page a signed-out visitor sees before choosing to sign in/up.
// Flow: Welcome ("/") -> Login/Signup ("/login") -> Pricing ("/pricing").
export default function WelcomePage() {
  const router = useRouter();
  // FIX: body is `h-screen overflow-hidden` in layout.tsx, so the window
  // itself never scrolls. useScroll() without a `container` option tracks
  // window scroll by default -- so scrollYProgress was permanently stuck at
  // its starting value, even though `main` (the actual visible scrollbar)
  // was scrolling just fine. That mismatch is why the animation never ran,
  // the glowing paths stayed nearly invisible (dim), and sticky positioning
  // looked cramped. Fix: make this wrapper its own explicit scroll owner
  // (containerRef, with a real height) and point useScroll at it directly.
  const containerRef = React.useRef<HTMLDivElement>(null);
  const targetRef = React.useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    container: containerRef,
    target: targetRef,
    offset: ['start start', 'end start'],
  });

  const pathLengthFirst = useTransform(scrollYProgress, [0, 0.8], [0.2, 1.2]);
  const pathLengthSecond = useTransform(scrollYProgress, [0, 0.8], [0.15, 1.2]);
  const pathLengthThird = useTransform(scrollYProgress, [0, 0.8], [0.1, 1.2]);
  const pathLengthFourth = useTransform(scrollYProgress, [0, 0.8], [0.05, 1.2]);
  const pathLengthFifth = useTransform(scrollYProgress, [0, 0.8], [0, 1.2]);

  return (
    <div
      ref={containerRef}
      className="h-full w-full overflow-y-auto no-scrollbar bg-black text-[var(--color-text-primary)]"
    >
      <div
        ref={targetRef}
        className="h-[400vh] bg-black w-full dark:border dark:border-white/[0.1] rounded-md relative overflow-clip"
      >
        <GoogleGeminiEffect
          pathLengths={[
            pathLengthFirst,
            pathLengthSecond,
            pathLengthThird,
            pathLengthFourth,
            pathLengthFifth,
          ]}
        />
      </div>

      <section className="h-screen w-full flex flex-col items-center justify-center gap-8 sm:gap-10 bg-black px-4">
        <CommitsGrid text="Xoltra" />
        <Button size="lg" onClick={() => router.push('/login')}>
          Sign In / Sign Up
        </Button>
      </section>
    </div>
  );
}
