'use client';
import { Inter, JetBrains_Mono, Source_Serif_4 } from "next/font/google";
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

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});
const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});
// FIX: globals.css already referenced --font-tiempo but nothing ever loaded
// a font into it. Tiempo Text itself is a licensed typeface (NYT/Klim) --
// Source Serif 4 stands in until real Tiempo files are self-hosted.
const tiempo = Source_Serif_4({
  variable: "--font-tiempo",
  subsets: ["latin"],
});

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
      <body className={`${inter.variable} ${jetbrainsMono.variable} ${tiempo.variable} antialiased h-screen overflow-hidden flex bg-[var(--color-bg-main)] text-[var(--color-text-primary)]`}>
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
