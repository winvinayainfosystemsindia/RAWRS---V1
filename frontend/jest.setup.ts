import "@testing-library/jest-dom";
import "jest-axe/extend-expect";

// jsdom doesn't implement window.matchMedia (a well-known gap, not a
// project-specific one) — ThemeProvider reads it to pick an initial
// light/dark default, so any test rendering it needs this stubbed once,
// globally, rather than per test file.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
