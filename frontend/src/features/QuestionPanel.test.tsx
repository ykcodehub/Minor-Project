import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import QuestionPanel from "./QuestionPanel";
vi.mock("../app/language", () => ({
  useLanguage: () => ({ t: (s: string) => s }),
}));
vi.mock("../app/session", () => ({
  useSession: () => ({ user: { id: "s", guest: true, is_guest: true } }),
}));
const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());
function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <QuestionPanel
        analysisId="s"
        sourceCount={1}
        disabled={false}
        onCitation={() => {}}
      />
    </QueryClientProvider>,
  );
}
describe("Ask Veriora failures", () => {
  it("shows actual API quota guidance and retry delay without inventing an answer", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          message: "Ask Veriora unavailable: PROVIDER_RATE_LIMITED",
          code: "PROVIDER_RATE_LIMITED",
        }),
        { status: 503, headers: { "Retry-After": "90" } },
      ),
    );
    mount();
    fireEvent.change(screen.getByLabelText("Your document question"), {
      target: { value: "What does the source state?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/rate-limited/)).toBeInTheDocument();
    expect(screen.getByText(/retry delay.*90/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Page/ }),
    ).not.toBeInTheDocument();
  });
  it("distinguishes insufficient evidence from provider failure", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          answer: "I cannot confirm this from the available document.",
          citations: [],
          limitations: [],
          reason_code: "INSUFFICIENT_VERIFIED_EVIDENCE",
        }),
        { status: 200 },
      ),
    );
    mount();
    fireEvent.change(screen.getByLabelText("Your document question"), {
      target: { value: "Is something missing?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(
      await screen.findByText(/No verified answer was established/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
