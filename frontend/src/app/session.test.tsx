import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import { SessionProvider, useSession } from "./session";
import { api, post } from "../lib/api";
vi.mock("../lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/api")>();
  return { ...original, api: vi.fn(), post: vi.fn() };
});
const profile = {
  id: "first-user",
  is_guest: true,
  csrf_token: "synthetic",
  retention_days: 1,
  providers: [],
};
beforeEach(() => vi.clearAllMocks());
function Controls() {
  const session = useSession();
  return (
    <>
      <span>{session.user?.id || "signed out"}</span>
      <button onClick={() => void session.ensure()}>Ensure guest</button>
      <button onClick={() => void session.refresh()}>Refresh session</button>
      <button onClick={() => void session.clear()}>Clear session</button>
    </>
  );
}
it("reuses the current guest after asynchronous source ingestion", async () => {
  vi.mocked(api).mockResolvedValue(profile);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <Controls />
      </SessionProvider>
    </QueryClientProvider>,
  );
  await screen.findByText("first-user");
  fireEvent.click(screen.getByText("Ensure guest"));
  await waitFor(() => expect(vi.mocked(post)).not.toHaveBeenCalled());
});
it("clears previous private data before switching the active account", async () => {
  vi.mocked(api).mockResolvedValue(profile);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  client.setQueryData(["sources"], [{ id: "private-document" }]);
  render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <Controls />
      </SessionProvider>
    </QueryClientProvider>,
  );
  await screen.findByText("first-user");
  vi.mocked(api).mockResolvedValue({ ...profile, id: "second-user" });
  fireEvent.click(screen.getByText("Refresh session"));
  await screen.findByText("second-user");
  expect(client.getQueryData(["sources"])).toBeUndefined();
});

it("clears client identity and private queries without another authenticated request", async () => {
  vi.mocked(api).mockResolvedValue(profile);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  client.setQueryData(["sources"], [{ id: "private-document" }]);
  render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <Controls />
      </SessionProvider>
    </QueryClientProvider>,
  );
  await screen.findByText("first-user");
  fireEvent.click(screen.getByText("Clear session"));
  await screen.findByText("signed out");
  expect(client.getQueryData(["sources"])).toBeUndefined();
  expect(vi.mocked(api)).toHaveBeenCalledTimes(1);
});
