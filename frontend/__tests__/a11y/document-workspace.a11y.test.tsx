import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
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
});
