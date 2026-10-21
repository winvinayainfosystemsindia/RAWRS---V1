import { render, screen } from "@testing-library/react";
import UploadPage from "@/app/(site)/page";

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn() }) }));

test("the upload page offers the read-only sample document", () => {
  render(<UploadPage />);
  expect(screen.getByRole("link", { name: /Explore a sample document/ })).toHaveAttribute("href", "/documents/demo");
});
