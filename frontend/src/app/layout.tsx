'use client';
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { FallbackToast } from "@/components/ui/FallbackToast";
import { UpgradeModal } from "@/components/ui/UpgradeModal";
import { SuspendedAccountModal } from "@/components/ui/SuspendedAccountModal";
import { TermsConsentGate } from "@/components/auth/TermsConsentGate";
import { useSystemStore } from "@/stores";
import { useEffect } from "react";
import { usePathname } from "next/navigation";

// FIX: previously used next/font/google (Inter, JetBrains_Mono, Source_Serif_4),
// which requires fetching font files from fonts.gstatic.com at dev-server
// startup. On VPNs / locked-down networks that fetch gets blocked, breaking
// the whole app with a "Module not found" error. Switched to system font
// stacks defined directly in globals.css (--font-inter / --font-jetbrains-mono
// / --font-tiempo) so nothing needs to be downloaded at all. If you want the
// real Inter/JetBrains Mono/Source Serif 4 look later, self-host the .woff2
// files under public/fonts and use next/font/local instead.

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const { fetchStatus } = useSystemStore();
  const pathname = usePathname();
  // Public pages (welcome + login) render standalone, no app chrome.
  const isPublicPage = pathname === '/' || pathname === '/login';

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(() => {
      fetchStatus();
    }, 1500);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  return (
    <html lang="en">
      <head>
        <title>Xoltra | Automation Platform</title>
      </head>
      <body className="antialiased h-screen overflow-hidden flex bg-[var(--color-bg-main)] text-[var(--color-text-primary)]">
        <CommandPalette />
        <FallbackToast />
        <UpgradeModal />
        <SuspendedAccountModal />
        <TermsConsentGate />
        {isPublicPage ? (
          <main className="flex-1 overflow-y-auto overflow-x-hidden relative">
            {children}
          </main>
        ) : (
          <>
            <Sidebar />
            <div className="flex-1 flex flex-col min-w-0">
              <Topbar />
              <main className="flex-1 overflow-y-auto overflow-x-hidden relative">
                {children}
              </main>
            </div>
          </>
        )}
      </body>
    </html>
  );
}
