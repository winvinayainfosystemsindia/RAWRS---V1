import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { BackendStatusNotice } from "@/components/BackendStatusNotice";
import { api } from "@/lib/api";

let mockPathname = "/";
jest.mock("next/navigation", () => ({ usePathname: () => mockPathname }));

afterEach(() => {
  jest.restoreAllMocks();
  mockPathname = "/";
});

test("stays out of the way on the sample document, which needs no server", async () => {
  mockPathname = "/documents/demo";
  const probe = jest.spyOn(api, "isBackendReachable").mockResolvedValue(false);
  const { container } = render(<BackendStatusNotice />);
  await waitFor(() => expect(probe).toHaveBeenCalled());
  expect(container).toBeEmptyDOMElement();
});

test("says nothing while the processing server is reachable", async () => {
  jest.spyOn(api, "isBackendReachable").mockResolvedValue(true);
  const { container } = render(<BackendStatusNotice />);
  await waitFor(() => expect(container).toBeEmptyDOMElement());
});

test("explains that the server is offline and how to request access", async () => {
  jest.spyOn(api, "isBackendReachable").mockResolvedValue(false);
  const { container } = render(<BackendStatusNotice />);

  expect(
    await screen.findByRole("heading", { name: "The RAWRS processing service is currently offline" })
  ).toBeInTheDocument();
  expect(screen.getByText(/contact the project owner and request access/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "View sample document" })).toHaveAttribute("href", "/documents/demo");
  expect(await axe(container)).toHaveNoViolations();
});

test("checks again on request and disappears once the server is up", async () => {
  const probe = jest.spyOn(api, "isBackendReachable").mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  const { container } = render(<BackendStatusNotice />);
  fireEvent.click(await screen.findByRole("button", { name: "Check again" }));
  await waitFor(() => expect(container).toBeEmptyDOMElement());
  expect(probe).toHaveBeenCalledTimes(2);
});
