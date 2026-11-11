import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SourceViewer } from "./SourceViewer";
const data = {
  kind: "upload",
  original_name: "synthetic.pdf",
  coverage: { pages_total: 2 },
  sections: Array.from({ length: 36 }, (_, i) => ({
    id: `sec-${i}`,
    ordinal: i,
    page: i < 18 ? 1 : 2,
    text: `Original block ${i}`,
  })),
};
vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data, isPending: false }),
}));
vi.mock("../app/language", () => ({
  useLanguage: () => ({ t: (s: string) => s }),
}));
Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  value: vi.fn(),
  configurable: true,
});
describe("PDF page grouping", () => {
  it("shows two original pages rather than 36 blocks and preserves exact highlights", () => {
    const { rerender } = render(<SourceViewer sourceId="s" />);
    expect(screen.getByText("/ 2")).toBeInTheDocument();
    expect(screen.getByText("Original block 17")).toBeInTheDocument();
    expect(screen.queryByText("Original block 18")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Next source section" }),
    );
    expect(screen.getByText("Original block 18")).toBeInTheDocument();
    rerender(
      <SourceViewer
        sourceId="s"
        citation={{
          source_id: "s",
          section_id: "sec-35",
          page: 2,
          quote: "block 35",
          start: 9,
          end: 17,
          match_status: "EXACT",
        }}
      />,
    );
    expect(screen.getByText("block 35").tagName).toBe("MARK");
    expect(
      screen.getByRole("button", { name: "Next source section" }),
    ).toBeDisabled();
  });
});
