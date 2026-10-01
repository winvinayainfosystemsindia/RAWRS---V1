import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";

// The site chrome - header, centred column, footer - for the pages that are
// read like a website (upload, recent documents). The document workspace is
// an application and takes the whole window, so it lives outside this group.
export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="border-b border-border bg-surface-panel">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-base font-bold tracking-wide text-text-primary">
              RAWRS
            </Link>
            <span className="hidden border-l border-border pl-4 text-xs font-medium uppercase tracking-wider text-text-secondary sm:block">
              Accessibility Verification &amp; Remediation Engine
            </span>
          </div>
          <nav className="flex items-center gap-4">
            <Link
              href="/"
              className="rounded text-sm text-text-secondary transition-colors hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              New Document
            </Link>
            <Link
              href="/documents"
              className="rounded text-sm text-text-secondary transition-colors hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              Documents
            </Link>
            <Link
              href="/settings"
              className="rounded text-sm text-text-secondary transition-colors hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              Settings
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
    </>
  );
}
