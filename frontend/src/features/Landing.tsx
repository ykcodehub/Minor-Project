import { useLanguage } from "../app/language";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  FileSearch,
  FileText,
  Link2,
  ScanText,
  Upload,
} from "lucide-react";
export default function Landing() {
  const { t } = useLanguage();

  const [selected, setSelected] = useState(false);
  return (
    <>
      <section className="hero page">
        <div className="hero-copy">
          <p className="eyebrow">
            <span className="line" /> {t("LEGAL DOCUMENT INTELLIGENCE")}
          </p>
          <h1>
            {t("Understand every clause.")}
            <br />
            <em>{t("Verify every claim.")}</em>
          </h1>
          <p className="hero-description">
            {t(
              "Turn complex agreements into clear, checkable findings. See what your documents say, what they mean, and exactly where the evidence lives.",
            )}
          </p>
          <div className="actions">
            <Link to="/demo/offline" className="button secondary">
              {t("Open offline synthetic demo")}
            </Link>
            <Link to="/analyze" className="button">
              {t("Analyze a document")}
              <ArrowUpRight size={18} />
            </Link>
            <a className="text-link" href="#verification">
              {t("How verification works")}
              <ArrowRight size={17} />
            </a>
          </div>
          <p className="hero-note">
            <FileText size={16} />{" "}
            {t("PDF, DOCX, TXT, HTML & website policies")}
          </p>
        </div>
        <div
          className="example-workspace"
          aria-label={t("Illustrative evidence workspace")}
        >
          <div className="example-title">
            <FileText size={18} />
            <span>{t("Service agreement")}</span>
            <span className="example-label">{t("Illustrative example")}</span>
          </div>
          <div className="example-document">
            <p className="eyebrow">{t("SECTION 7.2 · CANCELLATION")}</p>
            <h3>{t("The details make the difference.")}</h3>
            <p>
              {"You may cancel your subscription at any time."}{" "}
              <mark className={selected ? "selected" : ""}>
                {
                  "Cancellation takes effect at the end of the current billing period. Fees already paid are non-refundable, except where required by law."
                }
              </mark>
            </p>
            <div className="example-source-rule" />
          </div>
          <button
            className={`example-finding ${selected ? "active" : ""}`}
            onClick={() => setSelected(!selected)}
            aria-pressed={selected}
          >
            <div className="row between">
              <span className="tiny-label">{t("POTENTIAL CONCERN")}</span>
              <ArrowUpRight size={18} />
            </div>
            <h3>{t("Cancellation doesn’t mean a refund.")}</h3>
            <p>
              {t(
                "This example clause limits refunds, with an exception for legal requirements.",
              )}
            </p>
            <span className="text-link">
              {selected
                ? t("Source passage highlighted")
                : t("Inspect the example source")}{" "}
              <ArrowRight size={15} />
            </span>
          </button>
          <div className="example-bottom">
            <Check size={15} />{" "}
            {t("Every interpretation should come with evidence.")}
          </div>
        </div>
      </section>
      <div className="trust-strip page">
        <span className="tiny-label">
          {t("BUILT FOR THE DOCUMENTS THAT MATTER")}
        </span>
        <div>
          <span>{t("Privacy policies")}</span>
          <span>{t("Employment contracts")}</span>
          <span>{t("Terms & conditions")}</span>
          <span>{t("NDAs & service agreements")}</span>
        </div>
      </div>
      <section className="section page" id="verification">
        <div className="section-heading">
          <p className="eyebrow">{t("A CLEARER WAY TO READ THE FINE PRINT")}</p>
          <h2>
            {t("From a long document")}
            <br />
            {t("to a traceable understanding.")}
          </h2>
          <p className="muted">
            {t(
              "Read the interpretation. Inspect the source. Keep the context.",
            )}
          </p>
        </div>
        <div className="steps">
          <article>
            <span className="step-number">01</span>
            <Upload size={25} />
            <h3>{t("Bring your document")}</h3>
            <p>
              {t(
                "Upload a file, paste text, or discover policies linked from an official website.",
              )}
            </p>
            <Link to="/analyze" className="text-link">
              {t("Choose a source")}
              <ArrowRight size={16} />
            </Link>
          </article>
          <article>
            <span className="step-number">02</span>
            <FileSearch size={25} />
            <h3>{t("Understand the important parts")}</h3>
            <p>
              {t(
                "Explore rights, obligations, restrictions and exceptions. See extraction gaps and uncertainty.",
              )}
            </p>
          </article>
          <article>
            <span className="step-number">03</span>
            <BookOpen size={25} />
            <h3>{t("Follow every finding to evidence")}</h3>
            <p>
              {t(
                "Inspect exact passages, source locations and verification details in an Evidence Passport.",
              )}
            </p>
          </article>
        </div>
      </section>
      <section className="principle page">
        <div>
          <p className="eyebrow">{t("EVIDENCE BEFORE ASSERTION")}</p>
          <h2>
            {t("A policy is a statement.")}
            <br />
            {t("It isn’t proof of conduct.")}
          </h2>
        </div>
        <div>
          <p>
            {t(
              "Veriora distinguishes the document’s wording from an AI interpretation. A verified finding means the interpretation was checked against the captured source.",
            )}
          </p>
          <p className="muted">
            {t(
              "It does not establish real-world compliance, legal enforceability, or court admissibility. Missing evidence stays missing.",
            )}
          </p>
        </div>
      </section>
      <section className="section page">
        <div className="section-heading">
          <p className="eyebrow">{t("YOUR SOURCE. YOUR CHOICE.")}</p>
          <h2>{t("Start with what you have.")}</h2>
        </div>
        <div className="entry-methods">
          {[
            {
              Icon: Upload,
              title: t("Upload a document"),
              copy: t("Keep the original file and inspect its extracted text."),
              mode: "file",
            },
            {
              Icon: ScanText,
              title: t("Paste document text"),
              copy: t(
                "Go straight from a clause or agreement to structured analysis.",
              ),
              mode: "text",
            },
            {
              Icon: Link2,
              title: t("Discover website policies"),
              copy: t(
                "Review accessible official links and select your sources.",
              ),
              mode: "url",
            },
          ].map(({ Icon, title, copy, mode }) => (
            <Link
              key={mode}
              className="entry-method"
              to={`/analyze?mode=${mode}`}
            >
              <Icon size={23} />
              <h3>{title}</h3>
              <p>{copy}</p>
              <ArrowUpRight size={19} />
            </Link>
          ))}
        </div>
      </section>
      <section className="section page faq">
        <div>
          <p className="eyebrow">{t("BEFORE YOU BEGIN")}</p>
          <h2>
            {t("Clarity includes")}
            <br />
            {t("knowing the limits.")}
          </h2>
          <p className="muted">
            {t("You stay in control of your documents and processing choices.")}
          </p>
        </div>
        <div>
          {[
            [
              t("Where are my documents sent?"),
              t(
                "You choose a configured AI provider before analysis. External processing requires explicit consent. Confidential mode does not send content to external providers. Provider retention terms may differ.",
              ),
            ],
            [
              t("What happens to scanned PDFs?"),
              t(
                "The initial release extracts embedded text. Image-only pages are flagged as requiring OCR, with coverage gaps shown instead of invented content.",
              ),
            ],
            [
              t("Can I rely on this as legal advice?"),
              t(
                "No. Veriora helps you inspect document language and AI interpretations. Consult a qualified professional for legal advice or decisions.",
              ),
            ],
            [
              t("Can I delete my data?"),
              t(
                "Your library provides document deletion. Settings disclose retention and account controls. Provider-side retention is governed separately by the provider.",
              ),
            ],
          ].map(([question, answer]) => (
            <details key={question}>
              <summary>{question}</summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </section>
      <section className="closing page">
        <p className="eyebrow">
          {t("READ WITH CONTEXT. DECIDE WITH CLARITY.")}
        </p>
        <h2>{t("Make the fine print visible.")}</h2>
        <Link className="button" to="/analyze">
          {t("Analyze a document")}
          <ArrowUpRight size={18} />
        </Link>
      </section>
    </>
  );
}
