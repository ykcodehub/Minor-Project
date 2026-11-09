import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import SmartSummary, { type SummaryData } from "./SmartSummary";
import type { Finding } from "../lib/types";
const finding: Finding = {
  finding_id: "f",
  statement: "A duty",
  rationale: "Stated duty",
  category: "OBLIGATION",
  support_status: "SUPPORTED",
  qualifications: [],
  citations: [
    {
      source_id: "s",
      section_id: "sec",
      quote: "Original unchanged quotation.",
      start: 0,
      end: 29,
      match_status: "EXACT",
      page: 2,
    },
  ],
};
const data: SummaryData = {
  translation_ready: true,
  translations: {
    f: { statement: "दायित्व", rationale: "स्पष्टीकरण", qualifications: [] },
  },
  summary: {
    level: "Moderate",
    rule: "Documented test rule",
    rule_version: "test",
    disclaimer: "Not actual conduct",
    groups: { obligations: [finding] },
  },
};
describe("smart summary", () => {
  it.each(["en", "hi", "hinglish"] as const)(
    "preserves original source and navigates in %s",
    (language) => {
      const select = vi.fn();
      render(
        <SmartSummary data={data} language={language} onSelect={select} />,
      );
      expect(
        screen.getByText("Original unchanged quotation."),
      ).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button"));
      expect(select).toHaveBeenCalledWith(finding);
    },
  );
});
