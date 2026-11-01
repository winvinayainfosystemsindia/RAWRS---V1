import { act, renderHook } from "@testing-library/react";
import { api } from "@/lib/api";
import { useReviewTimer } from "@/lib/hooks/useReviewTimer";

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("useReviewTimer", () => {
  let post: jest.SpyInstance;

  beforeEach(() => {
    jest.useFakeTimers();
    setVisibility("visible");
    post = jest.spyOn(api, "postReviewTime").mockImplementation(() => undefined);
  });

  afterEach(() => {
    post.mockRestore();
    jest.useRealTimers();
  });

  it("counts strict time only within 60 s of input, loose within 300 s, and flushes when hidden", () => {
    renderHook(() => useReviewTimer("job1"));
    act(() => {
      jest.advanceTimersByTime(30_000); // 30 s right after "input" (mount)
    });
    expect(post).not.toHaveBeenCalled();
    act(() => {
      jest.advanceTimersByTime(29_000);
      setVisibility("hidden");
    });
    expect(post).toHaveBeenLastCalledWith("job1", 59, 59);
    act(() => {
      jest.advanceTimersByTime(120_000); // hidden: nothing counts
      setVisibility("visible");
      window.dispatchEvent(new Event("pagehide"));
    });
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("keeps counting loose time while reading without input, and flushes every 60 s", () => {
    renderHook(() => useReviewTimer("job1"));
    act(() => {
      jest.advanceTimersByTime(120_000);
    });
    expect(post).toHaveBeenNthCalledWith(1, "job1", 60, 60);
    expect(post).toHaveBeenNthCalledWith(2, "job1", 0, 60);
  });

  it("does nothing when disabled", () => {
    const { unmount } = renderHook(() => useReviewTimer("job1", false));
    act(() => {
      jest.advanceTimersByTime(120_000);
    });
    unmount();
    expect(post).not.toHaveBeenCalled();
  });
});
