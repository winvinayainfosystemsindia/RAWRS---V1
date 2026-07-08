import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import { ThemeProvider, NO_FLASH_THEME_SCRIPT } from "@/lib/theme/ThemeProvider";
import { ThemeToggle } from "@/components/ThemeToggle";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const jetbrainsMono = JetBrains_Mono({ variable: "--font-jetbrains-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "RAWRS — Accessibility Verification & Remediation Engine",
  description:
    "Verifies Mathpix output against the original PDF and automatically applies deterministic accessibility remediation before generating accessible deliverables.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col bg-surface-canvas text-text-primary">
        <ThemeProvider>
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-accent focus:px-4 focus:py-2 focus:text-accent-contrast"
          >
            Skip to main content
          </a>
          <header className="bg-surface-panel border-b border-border">
            <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
              <div className="flex items-center gap-4">
                <Link href="/" className="text-base font-bold text-text-primary tracking-wide">
                  RAWRS
                </Link>
                <span className="hidden sm:block text-xs text-text-secondary font-medium uppercase tracking-wider border-l border-border pl-4">
                  Accessibility Verification &amp; Remediation Engine
                </span>
              </div>
              <nav className="flex items-center gap-4">
                <Link
                  href="/"
                  className="text-sm text-text-secondary hover:text-text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
                >
                  New Document
                </Link>
                <ThemeToggle />
              </nav>
            </div>
          </header>
          <main id="main-content" className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
            {children}
          </main>
          <footer className="border-t border-border bg-surface-canvas">
            <div className="mx-auto max-w-6xl px-6 py-4 text-xs text-text-secondary">
              RAWRS — Accessibility Verification &amp; Remediation Engine
            </div>
          </footer>
        </ThemeProvider>
      </body>
    </html>
  );
}
