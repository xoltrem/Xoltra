'use client';
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { useSystemStore } from "@/stores";
import { useEffect } from "react";
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});
const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const { fetchStatus } = useSystemStore();
  useEffect(() => {
    // Initial fetch
    fetchStatus();
    
    // Poll every 1.5s
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
      <body className={`${inter.variable} ${jetbrainsMono.variable} antialiased h-screen overflow-hidden flex bg-[var(--color-bg-main)] text-[var(--color-text-primary)]`}>
        <CommandPalette />
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Topbar />
          <main className="flex-1 overflow-y-auto overflow-x-hidden relative">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
