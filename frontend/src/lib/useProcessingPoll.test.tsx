import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useProcessingPoll } from "./useProcessingPoll";
afterEach(() => vi.useRealTimers());
it("bounds polling, allows explicit resume and resets for a different resource", () => {
  vi.useFakeTimers();
  const { result, rerender } = renderHook(
    ({ id }) => useProcessingPoll(id, 1000),
    { initialProps: { id: "first" } },
  );
  expect(result.current.paused).toBe(false);
  act(() => vi.advanceTimersByTime(1001));
  expect(result.current.paused).toBe(true);
  act(() => result.current.resume());
  expect(result.current.paused).toBe(false);
  act(() => vi.advanceTimersByTime(1001));
  expect(result.current.paused).toBe(true);
  rerender({ id: "second" });
  expect(result.current.paused).toBe(false);
});
