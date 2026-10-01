import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import UploadPage from "@/app/(site)/page";

// Landing / Upload page accessibility. Since the documents dashboard
// (plan item 6) took over the recent-documents list, this page renders
// synchronously — no listDocuments poll to wait for — so axe runs straight
// after render. next/navigation is mocked at the module boundary because
// the Run button's handler uses useRouter.
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

describe("Landing / Upload page accessibility", () => {
  it("has no automatically detectable accessibility violations", async () => {
    const { container } = render(<UploadPage />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
