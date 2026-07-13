import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next.js 16 blocks cross-origin dev requests (including the
  // webpack-hmr WebSocket) by default. Without this, opening the dev
  // server via 127.0.0.1 or a LAN IP (anything other than the exact
  // "localhost" host it printed) silently breaks HMR: the browser falls
  // back to full-page reloads every time the socket reconnects, which
  // wipes all client state — including any file picked in a <input
  // type="file"> — before a user can act on it.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // react-resizable-panels ships ESM-only output. next/jest derives its
  // Jest transformIgnorePatterns from this list (there is no working way
  // to override transformIgnorePatterns directly in jest.config.js when
  // using next/jest — it recomputes the pattern from transpilePackages),
  // so WorkspaceShell's accessibility test can render for real.
  transpilePackages: ["react-resizable-panels"],
};

export default nextConfig;
