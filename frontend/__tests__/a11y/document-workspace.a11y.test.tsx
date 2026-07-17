import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { NavChips } from "@/components/workspace/NavChips";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";

// Document Workspace (Phase F-2.1 minimum scope). WorkspaceShell is a pure
// presentational shell — center/rail/nav content comes in as props, so its
// own chrome (toolbar, view switcher, Focus Mode toggle, resize handles) is
// testable in isolation without PDF/DOCX rendering or any context provider.
describe("Document Workspace (WorkspaceShell) accessibility", () => {
  it("has no automatically detectable accessibility violations", async () => {
    const { container } = render(
      <ThemeProvider>
        <WorkspaceShell
          filename="sample.pdf"
          status="complete"
          documentVersion={1}
          elapsedSeconds={0}
          durationSeconds={12.3}
          nav={<nav aria-label="Document outline">Outline stub</nav>}
          mode="document"
          centerViews={{
            pdf: <div>PDF stub</div>,
            markdown: <div>Markdown stub</div>,
            docx: <div>DOCX stub</div>,
          }}
          rightRail={<aside aria-label="Object inspector">Inspector stub</aside>}
          specialView={<div>Special view stub</div>}
          bottomPanel={<div>Bottom panel stub</div>}
        />
      </ThemeProvider>
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  // Phase R-4 M3 — closes the coverage gap left by R-2 (toolbar
  // Search/Export/Focus Mode, quickNav chips) and R-3 (icons added to all
  // of the above, plus the readiness Score badge) shipping without a
  // corresponding accessibility test. Populates every optional toolbar
  // prop and quickNav so the icon-bearing buttons, the readiness badge,
  // the NavChips row, and Focus Mode's aria-pressed state are all present
  // in the tree axe scans, not just the baseline empty-shell case above.
  it("has no automatically detectable accessibility violations (toolbar + quick-jump chips populated)", async () => {
    const { container } = render(
      <ThemeProvider>
        <WorkspaceShell
          filename="sample.pdf"
          status="complete"
          documentVersion={2}
          elapsedSeconds={0}
          durationSeconds={12.3}
          nav={<nav aria-label="Document outline">Outline stub</nav>}
          mode="document"
          currentPage={3}
          readinessScore={0.92}
          readinessReady={false}
          onOpenSearch={() => {}}
          jobId="test-job"
          docxAvailable
          markdownAvailable
          reportAvailable
          docxStale={false}
          markdownStale={false}
          quickNav={
            <NavChips
              sections={[
                { id: "validation", label: "Validation", count: 2 },
                { id: "images", label: "Images", count: 0 },
                { id: "readiness", label: "Accessibility Readiness" },
              ]}
              activeSpecialView="validation"
              onSelect={() => {}}
            />
          }
          centerViews={{
            pdf: <div>PDF stub</div>,
            markdown: <div>Markdown stub</div>,
            docx: <div>DOCX stub</div>,
          }}
          rightRail={<aside aria-label="Object inspector">Inspector stub</aside>}
          specialView={<div>Special view stub</div>}
          bottomPanel={<div>Bottom panel stub</div>}
        />
      </ThemeProvider>
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
