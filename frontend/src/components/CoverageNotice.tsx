import { useLanguage } from "../app/language";
import { FileText } from "lucide-react";
import { Notice, Status } from "./ui";
export function coverageSummary(
  coverage: Record<string, unknown> = {},
  extraction = false,
) {
  const details: string[] = [];
  const pages = Number(coverage.pages_total || 0),
    sections = Number(coverage.sections_total || 0),
    chunks = Number(coverage.chunks_total || 0);
  if (pages > 0) {
    const done = Number(
      coverage.pages_extracted ?? coverage.pages_processed ?? 0,
    );
    details.push(`${done} of ${pages} pages extracted`);
  }
  if (sections > 0) {
    const done = coverage.sections_processed;
    details.push(
      extraction || done === undefined
        ? `${sections} extracted ${sections === 1 ? "section" : "sections"}`
        : `${done} of ${sections} sections analyzed`,
    );
  }
  if (chunks > 0)
    details.push(
      `${Number(coverage.chunks_processed || 0)} of ${chunks} chunks analyzed`,
    );
  return details.length
    ? details.join(" · ")
    : "Coverage is not available yet.";
}
export function CoverageNotice({
  coverage = {},
  state,
  extraction = false,
}: {
  coverage?: Record<string, unknown>;
  state?: string;
  extraction?: boolean;
}) {
  const { t } = useLanguage();

  const warnings = Array.isArray(coverage.warnings)
    ? coverage.warnings.filter((w): w is string => typeof w === "string")
    : [];
  return (
    <>
      <div className="coverage-bar">
        <FileText size={18} />
        <strong>
          {extraction ? t("Extraction coverage") : t("Processing coverage")}
        </strong>
        <span>{coverageSummary(coverage, extraction)}</span>
        {state && <Status value={state} />}
      </div>
      {warnings.map((w) => (
        <Notice warning key={w}>
          {w}
        </Notice>
      ))}
    </>
  );
}
