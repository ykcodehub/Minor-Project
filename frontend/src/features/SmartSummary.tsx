import { useState } from "react";
import type { Finding, Language } from "../lib/types";
import { useLanguage } from "../app/language";
import {
  ArrowRight,
  AlertTriangle,
  ShieldCheck,
  CircleHelp,
  Sparkles,
  Scale,
  ListChecks,
  Ban,
  FileWarning,
  Info,
  Quote,
} from "lucide-react";
export interface SummaryData {
  summary: {
    level: string;
    rule: string;
    rule_version: string;
    disclaimer: string;
    groups: Record<string, Finding[]>;
  };
  translations: Record<
    string,
    Pick<Finding, "statement" | "rationale" | "qualifications">
  >;
  translation_ready: boolean;
  fingerprint?: string;
  suggested_questions?: string[];
}
const copy = {
  en: {
    title: "Document summary",
    benefits: "Benefits & rights",
    obligations: "Your obligations",
    restrictions: "Restrictions",
    potential_risks: "Potential risks",
    exceptions: "Important exceptions",
    empty:
      "No supported finding in this category. This does not establish that a provision is absent.",
    note: "The document states these terms. This does not prove the company follows them in practice.",
    open: "View exact source",
    Low: "Low",
    Moderate: "Moderate",
    High: "High",
    "Not Determinable": "Not Determinable",
  },
  hi: {
    title: "दस्तावेज़ का सारांश",
    benefits: "लाभ और अधिकार",
    obligations: "आपके दायित्व",
    restrictions: "प्रतिबंध",
    potential_risks: "संभावित जोखिम",
    exceptions: "महत्वपूर्ण अपवाद",
    empty:
      "इस श्रेणी में समर्थित निष्कर्ष नहीं मिला। इसका अर्थ यह नहीं कि प्रावधान अनुपस्थित है।",
    note: "ये दस्तावेज़ में लिखी शर्तें हैं। इनसे कंपनी के वास्तविक व्यवहार की पुष्टि नहीं होती।",
    open: "मूल स्रोत देखें",
    Low: "कम",
    Moderate: "मध्यम",
    High: "उच्च",
    "Not Determinable": "निर्धारित नहीं किया जा सकता",
  },
  hinglish: {
    title: "Document ka summary",
    benefits: "Fayde aur rights",
    obligations: "Aapki zimmedariyan",
    restrictions: "Pabandiyan",
    potential_risks: "Possible risks",
    exceptions: "Zaroori exceptions",
    empty:
      "Is category mein supported finding nahi mili. Isse provision absent hona prove nahi hota.",
    note: "Ye document ki stated terms hain. Isse company ka actual behaviour prove nahi hota.",
    open: "Original source dekhein",
    Low: "Low",
    Moderate: "Moderate",
    High: "High",
    "Not Determinable": "Determine nahi kar sakte",
  },
};
export default function SmartSummary({
  data,
  language,
  onSelect,
}: {
  data: SummaryData;
  language: Language;
  onSelect: (finding: Finding) => void;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const copyText = copy[language];
  const { t } = useLanguage();
  const level = data.summary.level;
  const tone =
    level === "High"
      ? "high"
      : level === "Moderate"
        ? "moderate"
        : level === "Low"
          ? "low"
          : "unknown";
  const RiskIcon =
    tone === "low"
      ? ShieldCheck
      : tone === "unknown"
        ? CircleHelp
        : AlertTriangle;
  const groups = [
    "potential_risks",
    "restrictions",
    "obligations",
    "benefits",
    "exceptions",
  ];
  const icons = {
    benefits: Sparkles,
    obligations: ListChecks,
    restrictions: Ban,
    potential_risks: FileWarning,
    exceptions: Scale,
  };
  const total = new Set(
    Object.values(data.summary.groups)
      .flat()
      .map((f) => f.finding_id),
  ).size;
  return (
    <section
      className="smart-summary"
      lang={
        language === "hi" ? "hi" : language === "hinglish" ? "hi-Latn" : "en"
      }
    >
      <div className={`summary-hero risk-${tone}`}>
        <div className="summary-hero-copy">
          <p className="eyebrow">{t("Evidence-grounded overview")}</p>
          <h2>{copyText.title}</h2>
          <p>{copyText.note}</p>
          <div className="summary-meta">
            <span>
              <ShieldCheck size={15} />
              {total} {t("Supported clauses")}
            </span>
            <span>
              <Quote size={15} />
              {t("Original quotations preserved")}
            </span>
          </div>
        </div>
        <div className="summary-risk">
          <div className="risk-icon">
            <RiskIcon size={24} />
          </div>
          <div>
            <span className="tiny-label">{t("Overall document risk")}</span>
            <strong>{copyText[level as keyof typeof copyText] || level}</strong>
            <span className="small-copy">
              {t("Rule-based review priority, not a legal verdict")}
            </span>
          </div>
        </div>
      </div>
      {(tone === "high" || tone === "unknown") && (
        <div className={`summary-warning risk-${tone}`} role="note">
          <RiskIcon size={20} />
          <div>
            <strong>{t("Important warnings")}</strong>
            <p>{t(data.summary.rule)}</p>
          </div>
        </div>
      )}
      <div className="summary-layout">
        <div className="summary-grid">
          {groups.map((key) => {
            const findings = data.summary.groups[key] || [];
            const Icon = icons[key as keyof typeof icons];
            return (
              <section
                className={`summary-topic topic-${key} ${findings.length === 0 ? "topic-empty" : ""}`}
                key={key}
              >
                <header>
                  <div className="topic-icon">
                    <Icon size={19} />
                  </div>
                  <h3>{copyText[key as keyof typeof copyText]}</h3>
                  <span className="topic-count">{findings.length}</span>
                </header>
                {!findings.length ? (
                  <p className="summary-empty">{copyText.empty}</p>
                ) : (
                  findings
                    .slice(0, expanded[key] ? findings.length : 2)
                    .map((f) => {
                      const text = data.translations[f.finding_id] || f;
                      return (
                        <article className="summary-clause" key={f.finding_id}>
                          <h4>{text.statement}</h4>
                          <details className="clause-context">
                            <summary>{t("Source & context")}</summary>
                            <p>{text.rationale}</p>
                            {text.qualifications.length > 0 && (
                              <p className="summary-exception">
                                <Info size={14} />
                                <span>{text.qualifications.join(" ")}</span>
                              </p>
                            )}
                            <blockquote lang="und">
                              {f.citations[0]?.quote}
                            </blockquote>
                          </details>
                          <button
                            className="text-link"
                            onClick={() => onSelect(f)}
                          >
                            {copyText.open}
                            <span className="citation-locator">
                              {f.citations[0]?.page
                                ? `${t("Page")} ${f.citations[0].page}`
                                : t("Source section")}
                            </span>
                            <ArrowRight size={15} />
                          </button>
                        </article>
                      );
                    })
                )}
                {findings.length > 2 && (
                  <button
                    className="text-link summary-more"
                    onClick={() =>
                      setExpanded({ ...expanded, [key]: !expanded[key] })
                    }
                  >
                    {t(expanded[key] ? "Show less" : "Show more")} (
                    {findings.length})
                  </button>
                )}
              </section>
            );
          })}
        </div>
        <aside className="summary-method">
          <details>
            <summary>{t("How to read this summary")}</summary>
            <p>
              {t(
                "Only supported findings with validated source quotations appear here. Missing findings do not prove that a term is absent.",
              )}
            </p>
          </details>
          <details>
            <summary>{t("Transparent assessment rules")}</summary>
            <p>{t(data.summary.rule)}</p>
            <p className="small-copy muted">{data.summary.rule_version}</p>
          </details>
          <p className="small-copy muted">{t(data.summary.disclaimer)}</p>
        </aside>
      </div>
    </section>
  );
}
