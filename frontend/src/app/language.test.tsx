import messages from "../lib/messages.json";
import keys from "../lib/ui-keys.json";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { LanguageProvider, useLanguage } from "./language";
import { api } from "../lib/api";
vi.mock("./session", () => ({
  useSession: () => ({ user: { id: "owner", language: "en" } }),
}));
vi.mock("../lib/api", () => ({ api: vi.fn() }));
function Probe() {
  const { language, setLanguage, t } = useLanguage();
  return (
    <>
      <output>{language}</output>
      <h1>{t("Dashboard")}</h1>
      <blockquote>Original source quote.</blockquote>
      <button onClick={() => void setLanguage("hi")}>Hindi</button>
      <button onClick={() => void setLanguage("hinglish")}>Hinglish</button>
    </>
  );
}
beforeEach(() => {
  localStorage.clear();
  vi.mocked(api).mockReset();
  vi.mocked(api).mockResolvedValue({});
});
describe("global language", () => {
  it("updates immediately and persists without modifying source text", async () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Hindi" }));
    expect(screen.getByRole("status")).toHaveTextContent("hi");
    expect(screen.getByText("Original source quote.")).toBeInTheDocument();
    await waitFor(() =>
      expect(api).toHaveBeenCalledWith("/me/language", {
        method: "PATCH",
        body: JSON.stringify({ language: "hi" }),
      }),
    );
    expect(document.documentElement.lang).toBe("hi");
  });
  it("serializes rapid preference writes in user order", async () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Hindi" }));
    fireEvent.click(screen.getByRole("button", { name: "Hinglish" }));
    await waitFor(() => expect(api).toHaveBeenCalledTimes(2));
    expect(
      vi
        .mocked(api)
        .mock.calls.map((c) => JSON.parse(c[1]!.body as string).language),
    ).toEqual(["hi", "hinglish"]);
    expect(document.documentElement.lang).toBe("hi-Latn");
  });
});

it("covers every wired UI message in both languages", () => {
  const catalog = messages as Record<string, { hi: string; hinglish: string }>;
  for (const key of keys) {
    expect(catalog[key]?.hi?.trim(), key).toBeTruthy();
    expect(catalog[key]?.hinglish?.trim(), key).toBeTruthy();
  }
});
