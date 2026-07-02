import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "RAWRS — Accessibility Verification & Remediation Engine",
  description:
    "Verifies Mathpix output against the original PDF and automatically applies deterministic accessibility remediation before generating accessible deliverables.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-gray-50 text-gray-900">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-blue-600 focus:px-4 focus:py-2 focus:text-white"
        >
          Skip to main content
        </a>
        <header className="bg-slate-900 border-b border-slate-800">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <div className="flex items-center gap-4">
              <Link href="/" className="text-base font-bold text-white tracking-wide">
                RAWRS
              </Link>
              <span className="hidden sm:block text-xs text-slate-400 font-medium uppercase tracking-wider border-l border-slate-700 pl-4">
                Accessibility Verification &amp; Remediation Engine
              </span>
            </div>
            <nav>
              <Link
                href="/"
                className="text-sm text-slate-400 hover:text-white transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
              >
                New Document
              </Link>
            </nav>
          </div>
        </header>
        <main id="main-content" className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
          {children}
        </main>
        <footer className="border-t border-gray-200 bg-white">
          <div className="mx-auto max-w-6xl px-6 py-4 text-xs text-gray-400">
            RAWRS — Accessibility Verification &amp; Remediation Engine
          </div>
        </footer>
      </body>
    </html>
  );
}
