import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SmartSummary, { type SummaryData } from "./SmartSummary";
vi.mock("../app/language", () => ({
  useLanguage: () => ({ t: (s: string) => s }),
}));
const base: SummaryData = {
  summary: {
    level: "Not Determinable",
    rule: "Incomplete verification",
    rule_version: "test",
    disclaimer: "Not legal advice",
    groups: {},
    counts: { retained: 20, verified: 0, excluded: 20 },
    processing_state: "PARTIAL_COMPLETION",
    failure_codes: ["PROVIDER_CONTEXT_LIMIT"],
  },
  translations: {},
  translation_ready: true,
};
describe("evidence grounded summary", () => {
  it("shows real partial counts and failure reasons without empty success cards", () => {
    render(<SmartSummary data={base} language="en" onSelect={() => {}} />);
    expect(screen.getByText(/20 findings require review/)).toBeInTheDocument();
    expect(
      screen.getByText(/No interpretation has passed/),
    ).toBeInTheDocument();
    expect(screen.getByText(/^PROVIDER_CONTEXT_LIMIT:/)).toBeInTheDocument();
    expect(screen.queryByText("Benefits & rights")).not.toBeInTheDocument();
  });
  it("renders neutral verified categories with source navigation", () => {
    const finding = {
      finding_id: "f",
      statement: "Synthetic privacy term",
      category: "PRIVACY",
      support_status: "SUPPORTED",
      rationale: "Synthetic",
      qualifications: [],
      citations: [{ quote: "Exact original quote", page: 2 }],
    } as unknown as import("../lib/types").Finding;
    const selected = vi.fn();
    render(
      <SmartSummary
        data={{
          ...base,
          summary: {
            ...base.summary,
            groups: { privacy_consent: [finding] },
            counts: { verified: 1, retained: 1, excluded: 0 },
            processing_state: "COMPLETED",
          },
        }}
        language="en"
        onSelect={selected}
      />,
    );
    expect(screen.getByText("Privacy & consent")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /View exact source/ }));
    expect(selected).toHaveBeenCalledWith(finding);
    expect(screen.getByText("Exact original quote")).toBeInTheDocument();
  });
});

it("discloses partial translations without relabeling originals as translated", () => {
  render(
    <SmartSummary
      data={{
        ...base,
        translation_ready: false,
        translation_completed: 4,
        translation_total: 7,
      }}
      language="hi"
      onSelect={() => {}}
    />,
  );
  expect(
    screen.getByText(/Verified translations available.*4.*7/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Untranslated explanations remain/),
  ).toBeInTheDocument();
});
