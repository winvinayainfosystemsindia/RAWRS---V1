import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { api } from "@/lib/api";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

import UploadPage from "@/app/page";

// Landing / Upload (Phase F-2.1 minimum scope). next/navigation is mocked
// at the module boundary; the API module is imported for real and only
// its network-calling method is stubbed via jest.spyOn (a path-alias
// jest.mock("@/lib/api", ...) failed to resolve reliably under next/jest's
// module mapping — spying on the real, already-resolvable import sidesteps
// that instead of fighting it) so the test exercises the real component's
// rendering and accessibility tree without a live backend or router.
describe("Landing / Upload page accessibility", () => {
  it("has no automatically detectable accessibility violations", async () => {
    jest.spyOn(api, "listDocuments").mockResolvedValue([]);

    const { container, findByText } = render(<UploadPage />);

    // Wait for the initial recent-documents poll to resolve so the
    // "Loading…" text isn't still present when axe runs.
    await findByText(/no documents have been processed yet/i);

    expect(await axe(container)).toHaveNoViolations();
  });
});
