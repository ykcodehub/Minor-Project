import { AlertTriangle, ArrowRight, ShieldCheck, ScanLine } from "lucide-react";
import { useLanguage } from "../app/language";
import type { Finding } from "../lib/types";
import type { SummaryData } from "./SmartSummary";

export default function RiskDashboard({
  data,
  onSelect,
}: {
  data: SummaryData;
  onSelect: (f: Finding) => void;
}) {
  const { t } = useLanguage();
  const summary = data.summary;
  if (!summary.risk_counts) return null;
  const levels = ["Low", "Moderate", "High"];
  const classified = levels.reduce(
    (n, key) => n + (summary.risk_counts?.[key] || 0),
    0,
  );
  const coverage = summary.coverage || {};
  const critical = summary.risk_groups?.High || [];
  return (
    <section
      className="risk-dashboard"
      aria-label={t("Document risk dashboard")}
    >
      <div className="risk-dashboard-grid">
        <section className="risk-distribution panel">
          <div className="row between">
            <h3>
              <ScanLine size={18} />
              {t("Verified risk distribution")}
            </h3>
            <span className="small-copy muted">
              {classified} {t("classified findings")}
            </span>
          </div>
          <div
            className="risk-segments"
            role="img"
            aria-label={levels
              .map(
                (level) => `${t(level)}: ${summary.risk_counts?.[level] || 0}`,
              )
              .join(", ")}
          >
            {classified ? (
              levels.map((level) => (
                <span
                  key={level}
                  className={`segment-${level.toLowerCase()}`}
                  style={{ flex: summary.risk_counts?.[level] || 0 }}
                />
              ))
            ) : (
              <span className="segment-unassessed" style={{ flex: 1 }} />
            )}
          </div>
          <div className="risk-counts">
            {levels.map((level) => (
              <div
                key={level}
                className={`risk-count risk-${level.toLowerCase()}`}
              >
                <span>{t(`${level} Risk`)}</span>
                <strong>{summary.risk_counts?.[level] || 0}</strong>
              </div>
            ))}
          </div>
          <p className="small-copy muted">
            {t(
              "Counts describe classified verified findings, not probabilities or the safety of unassessed terms.",
            )}
          </p>
        </section>
        <section className="risk-assurance panel">
          <h3>
            <ShieldCheck size={18} />
            {t("Evidence & coverage")}
          </h3>
          <dl>
            <div>
              <dt>{t("Verified")}</dt>
              <dd>{summary.counts?.verified || 0}</dd>
            </div>
            <div>
              <dt>{t("Needs review")}</dt>
              <dd>{summary.counts?.excluded || 0}</dd>
            </div>
            <div>
              <dt>{t("Unassessed")}</dt>
              <dd>{summary.risk_counts.Unassessed || 0}</dd>
            </div>
            <div>
              <dt>{t("Source sections processed")}</dt>
              <dd>
                {coverage.sections_processed || 0} /{" "}
                {coverage.sections_total || 0}
              </dd>
            </div>
          </dl>
          <p className="priority-index">
            {t("Review priority index")}:{" "}
            <strong>
              {summary.priority_index != null
                ? `${summary.priority_index} / 3`
                : t("Not Determinable")}
            </strong>
          </p>
          <details>
            <summary>{t("How this index works")}</summary>
            <p className="small-copy">
              {t(
                summary.priority_method ||
                  "No calibrated numerical risk score is available.",
              )}
            </p>
          </details>
        </section>
      </div>
      {!!critical.length && (
        <section
          className="critical-review"
          aria-label={t("Top critical issues")}
        >
          <header>
            <AlertTriangle size={20} />
            <div>
              <h3>{t("Top critical issues")}</h3>
              <p>
                {t(
                  "Review the exact wording, scope and exceptions before accepting these terms.",
                )}
              </p>
            </div>
            <span className="risk-tag risk-high">
              {critical.length} {t("High Risk")}
            </span>
          </header>
          {critical.slice(0, 3).map((f) => (
            <article key={f.finding_id} className="risk-item-high">
              <h4>{(data.translations[f.finding_id] || f).statement}</h4>
              <blockquote lang="und">{f.citations[0]?.quote}</blockquote>
              <p className="small-copy">
                {t(
                  summary.assessments?.[f.finding_id]?.reason ||
                    "Review this verified clause and its qualifications.",
                )}
              </p>
              <details>
                <summary>{t("Source & context")}</summary>
                <p>{(data.translations[f.finding_id] || f).rationale}</p>
                {(data.translations[f.finding_id] || f).qualifications?.map(
                  (q, i) => (
                    <p key={i}>{q}</p>
                  ),
                )}
              </details>
              <button className="text-link" onClick={() => onSelect(f)}>
                {t("View exact source")} |{" "}
                {f.citations[0]?.page
                  ? `${t("Page")} ${f.citations[0].page}`
                  : t("Source section")}
                <ArrowRight size={15} />
              </button>
            </article>
          ))}
        </section>
      )}
    </section>
  );
}
