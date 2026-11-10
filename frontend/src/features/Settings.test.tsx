import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Settings from "./Settings";
const mocks = vi.hoisted(() => ({
  api: vi.fn().mockResolvedValue({}),
  refresh: vi.fn().mockResolvedValue({}),
}));
vi.mock("../lib/api", () => ({
  api: mocks.api,
  download: vi.fn(),
  post: vi.fn(),
}));
vi.mock("../app/language", () => ({
  useLanguage: () => ({ t: (s: string) => s }),
}));
vi.mock("../app/session", () => {
  const user = {
    id: "u",
    retention_days: 30,
    preferred_provider: "gemini",
    authorized_providers: ["gemini"],
    providers: [
      { name: "gemini", model: "configured-gemini", configured: true },
      { name: "groq", model: "configured-groq", configured: true },
    ],
  };
  return {
    useSession: () => ({
      user,
      loading: false,
      refresh: mocks.refresh,
      clear: vi.fn(),
    }),
  };
});
describe("provider permission settings", () => {
  it("persists fallback permissions and supports revoking all", async () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /groq/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));
    await waitFor(() => expect(mocks.api).toHaveBeenCalled());
    expect(
      JSON.parse(mocks.api.mock.calls.at(-1)![1].body).authorized_providers,
    ).toEqual(["gemini", "groq"]);
    fireEvent.click(screen.getByRole("checkbox", { name: /gemini/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /groq/ }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Save preferences" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));
    await waitFor(() =>
      expect(
        JSON.parse(mocks.api.mock.calls.at(-1)![1].body).authorized_providers,
      ).toEqual([]),
    );
  });
});
