import { useState } from "react";
import { Link } from "react-router-dom";
import { Download, FileText, WifiOff } from "lucide-react";
import { useLanguage } from "../app/language";
import { Tabs } from "../components/Tabs";
import SmartSummary, { type SummaryData } from "./SmartSummary";
import type { Finding } from "../lib/types";
import fixture from "../demo/synthetic-agreement.json";

const findings = fixture.findings as Finding[];
const questions = {
  en: "When must invoices be paid?",
  hi: "बिलों का भुगतान कब करना होगा?",
  hinglish: "Invoices ka payment kab karna hoga?",
};

export default function OfflineDemo() {
  const { language, t } = useLanguage();
  const [tab, setTab] = useState("summary");
  const [selected, setSelected] = useState<Finding>();
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState("ALL");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<"saved" | "absent">();
  const translations = language === "en" ? {} : fixture.translations[language];
  const data: SummaryData = {
    summary: fixture.summary,
    translations,
    translation_ready: true,
  };
  function select(finding: Finding) {
    setSelected(finding);
    setPage(finding.citations[0].page || 1);
    setTab("detailed");
  }
  function exportReference() {
    const blob = new Blob([JSON.stringify(fixture, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "veriora-OFFLINE-AUTHORED-REFERENCE.json";
    link.click();
    URL.revokeObjectURL(url);
  }
  const payment = findings.find((f) => f.category === "PAYMENT")!;
  return (
    <section className="page offline-demo">
      <div className="notice warning" role="status">
        <WifiOff size={22} />
        <div>
          <strong>{t("Offline demo — authored reference, not live AI")}</strong>
          <p>
            {t(
              "Synthetic agreement only. Saved annotations and translations; exact quotations checked locally. No live semantic verification, provider request or private upload processing.",
            )}
          </p>
        </div>
      </div>
      <header className="page-heading">
        <div>
          <p className="eyebrow">{t("Synthetic two-page agreement")}</p>
          <h1>{t("Offline evidence workspace")}</h1>
        </div>
        <div className="actions">
          <a
            className="button secondary"
            href="/demo/synthetic-agreement.pdf"
            download
          >
            <Download size={16} />
            {t("Download synthetic PDF")}
          </a>
          <button className="button secondary" onClick={exportReference}>
            {t("Export offline reference")}
          </button>
          <Link className="text-link" to="/analyze">
            {t("Return to live analysis")}
          </Link>
        </div>
      </header>
      <Tabs
        label={t("Analysis views")}
        value={tab}
        onChange={setTab}
        items={[
          { value: "summary", label: t("Summary") },
          { value: "detailed", label: t("Detailed Analysis") },
          { value: "question", label: t("Saved demo question") },
        ]}
      />
      {tab === "summary" && (
        <SmartSummary data={data} language={language} onSelect={select} />
      )}
      {tab === "detailed" && (
        <>
          <div className="offline-demo-grid">
            <section className="panel">
              <h2>{t("Reference findings")}</h2>
              <label>
                {t("Category")}
                <select
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                >
                  <option value="ALL">{t("All categories")}</option>
                  {findings.map((finding) => (
                    <option key={finding.finding_id} value={finding.category}>
                      {finding.category}
                    </option>
                  ))}
                </select>
              </label>
              {findings
                .filter(
                  (finding) =>
                    category === "ALL" || finding.category === category,
                )
                .map((finding) => (
                  <article
                    key={finding.finding_id}
                    className={`offline-finding risk-item-${finding.risk_assessment?.level.toLowerCase()}`}
                  >
                    <span
                      className={`risk-tag risk-${finding.risk_assessment?.level.toLowerCase()}`}
                    >
                      {t(finding.risk_assessment?.level || "Unassessed")}
                    </span>
                    <p>
                      {
                        (data.translations[finding.finding_id] || finding)
                          .statement
                      }
                    </p>
                    <button
                      className="text-link"
                      onClick={() => select(finding)}
                    >
                      {t("View exact source")} · {t("Page")}{" "}
                      {finding.citations[0].page}
                    </button>
                    <details>
                      <summary>{t("Reference validation method")}</summary>
                      <p>
                        {t(
                          "Authored interpretation; exact source quotation validated. No independent AI review.",
                        )}
                      </p>
                      <p>{t(finding.risk_assessment?.reason || "")}</p>
                    </details>
                  </article>
                ))}
            </section>
            <section
              className="panel"
              aria-label={t("Synthetic source viewer")}
            >
              <h2>
                <FileText size={18} /> {t("Original source")}
              </h2>
              <div className="actions">
                {[1, 2].map((number) => (
                  <button
                    className="button secondary small"
                    key={number}
                    aria-pressed={page === number}
                    onClick={() => setPage(number)}
                  >
                    {t("Page")} {number}
                  </button>
                ))}
              </div>
              <p>
                {t("Page")} {page} / 2
              </p>
              {fixture.sections
                .filter((section) => section.page === page)
                .map((section) => (
                  <p
                    key={section.id}
                    lang="en"
                    className={
                      selected?.citations[0].section_id === section.id
                        ? "offline-source-selected"
                        : ""
                    }
                  >
                    {section.text}
                  </p>
                ))}
              <details>
                <summary>{t("Evidence Passport")}</summary>
                <p>{t("Synthetic reference only")}</p>
                <code className="offline-hash">SHA-256: {fixture.sha256}</code>
              </details>
            </section>
          </div>
          <details className="panel">
            <summary>{t("Processing Coverage")}</summary>
            <p>
              {t(
                "Offline reference: 2 pages, 7 exact quotations; no live model processing.",
              )}
            </p>
          </details>
        </>
      )}
      {tab === "question" && (
        <section className="panel">
          <h2>{t("Saved demo question")}</h2>
          <p>
            {t(
              "This is a saved reference answer, not generative chat. Other questions are unavailable offline.",
            )}
          </p>
          <button
            className="text-link"
            onClick={() => {
              setQuestion(questions[language]);
              setAnswer(undefined);
            }}
          >
            {questions[language]}
          </button>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setAnswer(
                Object.values(questions).some(
                  (q) => q.toLowerCase() === question.trim().toLowerCase(),
                )
                  ? "saved"
                  : "absent",
              );
            }}
          >
            <label>
              {t("Offline question")}
              <input
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                required
              />
            </label>
            <button className="button" type="submit">
              {t("Show saved answer")}
            </button>
          </form>
          {answer === "saved" && (
            <div role="status">
              <p>
                {(data.translations[payment.finding_id] || payment).statement}
              </p>
              <blockquote lang="en">{payment.citations[0].quote}</blockquote>
              <button className="text-link" onClick={() => select(payment)}>
                {t("View exact source")} · {t("Page")}{" "}
                {payment.citations[0].page}
              </button>
            </div>
          )}
          {answer === "absent" && (
            <p role="status">
              {t(
                "No saved answer for this question. Live AI is not running in offline demo mode.",
              )}
            </p>
          )}
        </section>
      )}
    </section>
  );
}
