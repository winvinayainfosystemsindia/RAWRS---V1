import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ThemeProvider, NO_FLASH_THEME_SCRIPT } from "@/lib/theme/ThemeProvider";
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
          {/* Site pages add their header/footer in app/(site)/layout.tsx; the
              document workspace fills the window with its own chrome. */}
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
