import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RiskDashboard from "./RiskDashboard";
import type { SummaryData } from "./SmartSummary";
import type { Finding } from "../lib/types";
vi.mock("../app/language", () => ({
  useLanguage: () => ({ t: (s: string) => s }),
}));
const finding = {
  finding_id: "high",
  statement: "Unlimited liability",
  support_status: "SUPPORTED",
  category: "RISK_NOTE",
  qualifications: [],
  rationale: "Stated",
  citations: [
    {
      source_id: "s",
      section_id: "r",
      page: 2,
      start: 0,
      end: 20,
      quote: "Exact original quote",
      match_status: "EXACT",
    },
  ],
} as Finding;
const data: SummaryData = {
  translation_ready: true,
  translations: {},
  summary: {
    level: "High",
    rule: "Rule",
    rule_version: "test",
    disclaimer: "Not legal advice",
    groups: {},
    risk_counts: { High: 2, Moderate: 4, Low: 1, Unassessed: 0 },
    risk_groups: { High: [finding] },
    counts: { verified: 7, retained: 7, excluded: 0 },
    coverage: { sections_processed: 36, sections_total: 36 },
    priority_index: 3,
  },
};
describe("risk dashboard", () => {
  it("charts actual classified counts, emphasizes high clauses and opens exact evidence", () => {
    const select = vi.fn();
    render(<RiskDashboard data={data} onSelect={select} />);
    expect(
      screen.getByRole("img", { name: "Low: 1, Moderate: 4, High: 2" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Unlimited liability").closest("article"),
    ).toHaveClass("risk-item-high");
    expect(screen.getByText("Exact original quote")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /View exact source/ }));
    expect(select).toHaveBeenCalledWith(finding);
    expect(screen.getByText("3 / 3")).toBeInTheDocument();
  });
  it("does not fabricate a score or chart unverified findings", () => {
    render(
      <RiskDashboard
        data={{
          ...data,
          summary: {
            ...data.summary,
            priority_index: null,
            risk_groups: {},
            risk_counts: { High: 0, Moderate: 0, Low: 0, Unassessed: 0 },
            counts: { verified: 0, retained: 7, excluded: 7 },
          },
        }}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText("Not Determinable")).toBeInTheDocument();
    expect(screen.queryByText("3 / 3")).not.toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Low: 0, Moderate: 0, High: 0" }),
    ).toBeInTheDocument();
  });
});
