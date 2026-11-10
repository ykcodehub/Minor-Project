import { providerFailure } from "../lib/providerFailure";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Copy,
  Download,
  FileSearch,
  MessageSquare,
  Search,
} from "lucide-react";
import { useProcessingPoll } from "../lib/useProcessingPoll";
import { api, apiPage, download, post } from "../lib/api";
import {
  active,
  type Analysis,
  type Finding,
  type Job,
  type Citation,
} from "../lib/types";
import { citationValid } from "../lib/evidence";
import { useSession } from "../app/session";
import { CoverageNotice } from "../components/CoverageNotice";
import SmartSummary, { type SummaryData } from "./SmartSummary";
import { useLanguage } from "../app/language";
import QuestionPanel from "./QuestionPanel";
import { Tabs } from "../components/Tabs";
import { pageOffset } from "../lib/query";
import { Pagination } from "../components/Pagination";
import { SourceViewer } from "../components/SourceViewer";
import {
  Empty,
  ErrorNotice,
  Loading,
  PageHeading,
  ProcessingPaused,
  Status,
} from "../components/ui";
function display(value: unknown) {
  return typeof value === "string" ? value : JSON.stringify(value);
}
export default function Workspace() {
  const { id = "" } = useParams();
  const polling = useProcessingPoll(id);
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const { user } = useSession();
  const [selectedId, setSelectedId] = useState(params.get("finding") || "");
  const [mobileTab, setMobileTab] = useState("insights");
  const [mode, setMode] = useState("summary");
  useEffect(() => {
    setMode("summary");
    setView("findings");
    setMobileTab("insights");
  }, [id]);
  const { language, t } = useLanguage();
  const [view, setView] = useState("findings");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const analysis = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => api<Analysis>(`/analyses/${id}`),
    refetchInterval: (q) =>
      !polling.paused && !q.state.error && active(q.state.data?.status)
        ? 1800
        : false,
  });
  const jobId = analysis.data?.job_id;
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api<Job>(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) =>
      !polling.paused && !q.state.error && active(q.state.data?.state)
        ? 1600
        : false,
  });
  const [answerCitation, setAnswerCitation] = useState<Citation>();
  const offset = pageOffset(params.get("offset"), 30);
  const findingQuery = new URLSearchParams({
    offset: String(offset),
    limit: "30",
  });
  for (const [urlKey, apiKey] of [
    ["q", "q"],
    ["category", "category"],
    ["status", "status"],
    ["source", "source_id"],
  ]) {
    const value = params.get(urlKey);
    if (value) findingQuery.set(apiKey, value);
  }
  if (view === "duties" && !params.get("category"))
    findingQuery.set(
      "category",
      "RIGHT,OBLIGATION,RESTRICTION,CONSENT,EXCEPTION",
    );
  const findings = useQuery({
    queryKey: ["findings", id, analysis.data?.status, findingQuery.toString()],
    queryFn: () => apiPage<Finding>(`/analyses/${id}/findings?${findingQuery}`),
    enabled: !!analysis.data,
    refetchInterval: (q) =>
      !q.state.error &&
      !polling.paused &&
      !analysis.error &&
      active(analysis.data?.status)
        ? 2500
        : false,
  });
  const selectedQuery = useQuery({
    queryKey: ["finding", id, selectedId],
    queryFn: () => api<Finding>(`/analyses/${id}/findings/${selectedId}`),
    enabled:
      !!selectedId &&
      !findings.data?.items.some((f) => f.finding_id === selectedId),
  });
  const summary = useQuery({
    queryKey: ["smart-summary", id, language, analysis.data?.status],
    queryFn: () =>
      api<SummaryData>(`/analyses/${id}/summary?language=${language}`),
    enabled: !!analysis.data,
  });
  async function prepareLanguage() {
    setBusy(true);
    setError(undefined);
    try {
      await post(`/analyses/${id}/translations?language=${language}`);
      await summary.refetch();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const translation = useQuery({
    queryKey: [
      "translation-preparation",
      id,
      language,
      summary.data?.fingerprint,
    ],
    queryFn: async () => {
      await post(`/analyses/${id}/translations?language=${language}`);
      await summary.refetch();
      return true;
    },
    enabled:
      !!user &&
      language !== "en" &&
      !!summary.data &&
      !summary.data.translation_ready &&
      ["COMPLETED", "PARTIAL_COMPLETION"].includes(analysis.data?.status || ""),
    retry: false,
    staleTime: Infinity,
  });
  const data = analysis.data;
  const all = useMemo(() => findings.data?.items || [], [findings.data?.items]);
  const selectedBase = selectedId
    ? all.find((f) => f.finding_id === selectedId) || selectedQuery.data
    : undefined;
  const selected = selectedBase
    ? {
        ...selectedBase,
        ...summary.data?.translations[selectedBase.finding_id],
      }
    : undefined;
  const citation = answerCitation || selected?.citations[0];
  const sourceId =
    citation?.source_id ||
    params.get("source") ||
    data?.source_ids?.[0] ||
    data?.sources?.[0]?.id;
  const source = data?.sources?.find((s) => s.id === sourceId);
  const state = job.data?.state || data?.status;
  const filtered = all.map((f) => ({
    ...f,
    ...summary.data?.translations[f.finding_id],
  }));
  function filter(key: string, value: string) {
    const p = new URLSearchParams(params);
    if (value) p.set(key, value);
    else p.delete(key);
    if (key !== "finding" && key !== "offset") p.delete("offset");
    setParams(p, { replace: true });
  }
  function select(f: Finding) {
    setAnswerCitation(undefined);
    setSelectedId(f.finding_id);
    filter("finding", f.finding_id);
    setMobileTab("source");
    setCopied(false);
  }
  useEffect(() => {
    setSelectedId(params.get("finding") || "");
  }, [params]);
  useEffect(() => {
    if (!selectedId && !answerCitation && all.length)
      setSelectedId(all[0].finding_id);
  }, [all, selectedId, answerCitation]);
  async function jobAction(action: string) {
    setBusy(true);
    setError(undefined);
    try {
      await post(`/jobs/${jobId}/${action}`);
      polling.resume();
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["analysis", id] }),
        qc.invalidateQueries({ queryKey: ["job", jobId] }),
      ]);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function exportReport(format: string) {
    setError(undefined);
    setBusy(true);
    try {
      await download(
        `/analyses/${id}/exports?format=${format}&language=${language}`,
        `veriora-${id}.${format}`,
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function copy() {
    setError(undefined);
    try {
      await navigator.clipboard.writeText(
        `${selected?.statement}\n“${citation?.quote}”\nSource ${sourceId}, section ${citation?.section_id}, ${citation?.page ? `page ${citation.page}, ` : ""}SHA-256 ${source?.sha256}`,
      );
      setCopied(true);
    } catch {
      setError(
        t(
          "Clipboard access is unavailable. Select and copy the reference text from the Evidence Passport.",
        ),
      );
    }
  }
  if (analysis.isPending)
    return <Loading label={t("Opening your analysis…")} />;
  if (analysis.error)
    return (
      <section className="page">
        <ErrorNotice error={analysis.error} />
        <Link to="/library">{t("Back to library")}</Link>
      </section>
    );
  return (
    <section className="page workspace-page">
      <Link className="back-link" to="/library">
        <ArrowLeft size={15} />
        {t("Document library")}
      </Link>
      <PageHeading
        eyebrow={t("ANALYSIS WORKSPACE")}
        title={
          data?.sources?.length === 1
            ? data.sources[0].original_name
            : `${data?.sources?.length || data?.source_ids?.length || 1} document analysis`
        }
        actions={
          <>
            <button
              className="button secondary"
              disabled={
                busy ||
                user?.guest ||
                !["COMPLETED", "PARTIAL_COMPLETION"].includes(state || "")
              }
              onClick={() => void exportReport("json")}
            >
              <Download size={16} />
              {t("Manifest")}
            </button>
            <button
              className="button"
              disabled={
                busy ||
                user?.guest ||
                !["COMPLETED", "PARTIAL_COMPLETION"].includes(state || "")
              }
              onClick={() => void exportReport("pdf")}
            >
              <Download size={16} />
              {t("PDF report")}
            </button>
          </>
        }
      >
        {t("Findings you can inspect. Source evidence you can follow.")}
      </PageHeading>
      {polling.paused && active(analysis.data?.status) && (
        <ProcessingPaused
          onResume={() => {
            polling.resume();
            void analysis.refetch();
            void job.refetch();
          }}
        />
      )}
      <div className="workspace-presentation">
        <Tabs
          label={t("Analysis presentation")}
          value={mode}
          onChange={setMode}
          items={[
            { value: "summary", label: t("Summary") },
            { value: "detailed", label: t("Detailed Analysis") },
          ]}
        />
        {language !== "en" && !summary.data?.translation_ready && (
          <div>
            <p className="muted small-copy">
              {t(
                "Original English explanations remain visible until translation is verified. Source quotes always stay unchanged. Uses your analysis provider.",
              )}
            </p>
            <button
              className="button secondary"
              disabled={busy || active(state)}
              onClick={() => void prepareLanguage()}
            >
              {t("Prepare verified translation")}
            </button>
          </div>
        )}
      </div>
      <ErrorNotice error={error || job.error || selectedQuery.error} />
      {user?.guest && (
        <p className="small-copy muted">
          <Link to="/sign-in">{t("Sign in")}</Link>{" "}
          {t("to export a report. Guest results are temporary.")}
        </p>
      )}
      {active(state) && (
        <section className="panel processing" aria-live="polite">
          <Loading
            label={`${job.data?.stage || t("Queued")} · ${job.data?.state || data?.status}`}
          />
          <p className="muted">
            {t(
              "You can safely leave this page. Processing continues on the server.",
            )}
          </p>
          {typeof job.data?.progress?.provider === "string" && (
            <p className="small-copy">
              {t("Current AI provider")}: {display(job.data.progress.provider)}{" "}
              / {display(job.data.progress.model)}
            </p>
          )}
          <details>
            <summary>{t("Processing details")}</summary>
            <div className="processing-stages">
              {["RECEIVED", "GENERATING", "VERIFYING", "AGGREGATING"].map(
                (s) => (
                  <span
                    key={s}
                    className={job.data?.stage === s ? "current" : ""}
                  >
                    {s.toLowerCase()}
                  </span>
                ),
              )}
            </div>
            {job.data?.progress && (
              <dl className="progress-units">
                {Object.entries(job.data.progress).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key.replaceAll("_", " ")}</dt>
                    <dd>{display(value)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </details>
          <button
            className="button secondary small"
            disabled={busy}
            onClick={() => void jobAction("cancel")}
          >
            {t("Cancel processing")}
          </button>
        </section>
      )}
      {["FAILED", "CANCELLED", "CANCELED"].includes(state || "") && (
        <div className="notice error">
          <FileSearch size={20} />
          <div>
            <strong>
              {state === "FAILED"
                ? t("Analysis could not be completed")
                : t("Processing was canceled")}
            </strong>
            <p>
              {job.data?.error ||
                t(
                  "No complete analysis is available. Preserved sources remain inspectable.",
                )}
            </p>
            {providerFailure(job.data?.error || "") && (
              <p>{t(providerFailure(job.data?.error || "")!)}</p>
            )}
            <button
              className="button secondary small"
              disabled={busy}
              onClick={() => void jobAction("retry")}
            >
              {t("Retry analysis")}
            </button>
          </div>
        </div>
      )}
      <ErrorNotice error={summary.error || translation.error} />
      {mode === "summary" && summary.isPending && <Loading />}
      {mode === "summary" && summary.data && (
        <SmartSummary
          data={summary.data}
          language={language}
          onSelect={(f) => {
            select(f);
            setMode("detailed");
            setView("findings");
            setMobileTab("source");
          }}
        />
      )}
      <div hidden={mode !== "detailed"}>
        <div className="workspace-nav">
          <Tabs
            label={t("Analysis views")}
            value={view}
            onChange={(key) => {
              setView(key);
              if (key === "duties") filter("category", "");
            }}
            items={[
              { value: "findings", label: "Findings" },
              { value: "duties", label: t("Rights & duties") },
              {
                value: "ask",
                label: (
                  <>
                    <MessageSquare size={16} />
                    {t("Ask Veriora")}
                  </>
                ),
              },
            ]}
          />
          <span className="muted small-copy">
            {data?.findings_count || 0} {t("findings")}
          </span>
        </div>
        {view === "ask" ? (
          <QuestionPanel
            analysisId={id}
            language={language}
            sourceCount={data?.source_ids?.length || 0}
            suggestions={summary.data?.suggested_questions || []}
            disabled={
              active(state) ||
              !["COMPLETED", "PARTIAL_COMPLETION"].includes(state || "")
            }
            onCitation={(c) => {
              if (citationValid(c)) {
                setAnswerCitation(c);
                setSelectedId("");
                setView("findings");
                setMobileTab("source");
              } else if (c.finding_id) {
                setSelectedId(c.finding_id);
                filter("finding", c.finding_id);
                setView("findings");
                setMobileTab("source");
              }
            }}
          />
        ) : (
          <>
            <Tabs
              className="mobile-workspace-tabs"
              label={t("Workspace panels")}
              value={mobileTab}
              onChange={setMobileTab}
              items={[
                { value: "insights", label: "Insights" },
                { value: "source", label: t("Source & evidence") },
              ]}
            />
            <div className="workspace-grid">
              <section
                className={`findings-panel ${mobileTab === "insights" ? "mobile-active" : ""}`}
              >
                <div className="finding-filters">
                  <label className="search-field">
                    <Search size={17} />
                    <span className="sr-only">{t("Search findings")}</span>
                    <input
                      placeholder={t("Search findings or source text")}
                      value={params.get("q") || ""}
                      onChange={(e) => filter("q", e.target.value)}
                    />
                  </label>
                  <div className="filter-row">
                    <label>
                      <span className="sr-only">{t("Finding category")}</span>
                      <select
                        value={params.get("category") || ""}
                        onChange={(e) => filter("category", e.target.value)}
                      >
                        <option value="">{t("All categories")}</option>
                        {[
                          "CLAUSE",
                          "OBLIGATION",
                          "RIGHT",
                          "RESTRICTION",
                          "CONSENT",
                          "EXCEPTION",
                          "RISK_NOTE",
                          "PRIVACY",
                          "PAYMENT",
                          "TERMINATION",
                          "DISPUTE",
                          "PERMISSION",
                          "OTHER",
                        ].map((c) => (
                          <option value={c} key={c}>
                            {t(c.replaceAll("_", " "))}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span className="sr-only">{t("Evidence status")}</span>
                      <select
                        value={params.get("status") || ""}
                        onChange={(e) => filter("status", e.target.value)}
                      >
                        <option value="">{t("All evidence states")}</option>
                        {[
                          "SUPPORTED",
                          "PARTIALLY_SUPPORTED",
                          "UNSUPPORTED",
                          "AMBIGUOUS",
                        ].map((s) => (
                          <option value={s} key={s}>
                            {t(s.replaceAll("_", " "))}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {(data?.sources?.length || 0) > 1 && (
                    <label>
                      {t("Source document")}
                      <select
                        value={params.get("source") || ""}
                        onChange={(e) => filter("source", e.target.value)}
                      >
                        <option value="">{t("All documents")}</option>
                        {data?.sources?.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.original_name}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                </div>
                <ErrorNotice error={findings.error} />
                {findings.isPending ? (
                  <Loading label={t("Loading findings…")} />
                ) : (
                  (view === "duties"
                    ? filtered.filter((f) =>
                        [
                          "RIGHT",
                          "OBLIGATION",
                          "RESTRICTION",
                          "CONSENT",
                          "EXCEPTION",
                        ].includes(f.category),
                      )
                    : filtered
                  ).map((f) => (
                    <article
                      className={`finding-card ${f.finding_id === selectedId ? "selected" : ""}`}
                      key={f.finding_id}
                    >
                      <div className="row between">
                        <span className="tiny-label">
                          {f.category.replaceAll("_", " ")}
                        </span>
                        <Status
                          value={f.support_status}
                          valid={
                            f.citations.length > 0 &&
                            f.citations.every(citationValid)
                          }
                        />
                      </div>
                      <h2>{f.statement}</h2>
                      <p>{f.rationale}</p>
                      {f.qualifications?.length > 0 && (
                        <p className="qualification">
                          {t("Qualification:")}
                          {f.qualifications.join(" ")}
                        </p>
                      )}
                      <div className="row between">
                        <span className="muted small-copy">
                          {f.citations[0]?.page
                            ? `${t("Page")} ${f.citations[0].page}`
                            : t("Source section")}
                          {f.citations[0]?.clause_label &&
                            ` · ${f.citations[0].clause_label}`}
                        </span>
                        <button
                          className="text-link"
                          onClick={() => select(f)}
                          aria-pressed={f.finding_id === selectedId}
                        >
                          {t("View evidence")}
                          <ArrowRight size={15} />
                        </button>
                      </div>
                    </article>
                  ))
                )}
                <Pagination
                  offset={offset}
                  total={findings.data?.total ?? null}
                  pageSize={30}
                  count={all.length}
                  onChange={(n) => filter("offset", String(n))}
                />
                {!findings.isPending && !filtered.length && (
                  <Empty
                    title={
                      active(state)
                        ? t("Findings are being prepared")
                        : findings.error
                          ? t("Findings unavailable")
                          : t("No findings in this view")
                    }
                  >
                    {active(state)
                      ? t(
                          "Results appear as the server completes verification.",
                        )
                      : t(
                          "Try changing filters. No findings does not establish that a term is absent or that the document is safe.",
                        )}
                  </Empty>
                )}
              </section>
              <aside
                className={`evidence-panel ${mobileTab === "source" ? "mobile-active" : ""}`}
              >
                {sourceId ? (
                  <div className="panel viewer-panel">
                    <SourceViewer sourceId={sourceId} citation={citation} />
                  </div>
                ) : (
                  <Empty title={t("No captured source available")} />
                )}
                {selected && (
                  <section className="panel passport">
                    <div className="row between">
                      <h2>{t("Evidence Passport")}</h2>
                      <button className="text-link" onClick={() => void copy()}>
                        <Copy size={15} />
                        {copied ? t("Copied") : t("Copy reference")}
                      </button>
                    </div>
                    <Status
                      value={selected.support_status}
                      valid={
                        selected.citations.length > 0 &&
                        selected.citations.every(citationValid)
                      }
                    />
                    <blockquote>
                      {citation?.quote ||
                        t("No source quotation was provided.")}
                    </blockquote>
                    <p>{selected.statement}</p>
                    <dl>
                      <dt>{t("Source document")}</dt>
                      <dd>{source?.original_name || citation?.source_id}</dd>
                      <dt>{t("Original source")}</dt>
                      <dd>
                        {source?.source_url ||
                          t("Uploaded file or pasted text")}
                      </dd>
                      <dt>{t("Source identifier / version")}</dt>
                      <dd className="mono">{sourceId}</dd>
                      <dt>{t("Acquired")}</dt>
                      <dd>
                        {source?.captured_at
                          ? new Date(source.captured_at).toLocaleString()
                          : t("Unavailable")}
                      </dd>
                      <dt>{t("Source SHA-256")}</dt>
                      <dd className="mono">
                        {source?.sha256 || t("Unavailable")}
                      </dd>
                      <dt>{t("Location")}</dt>
                      <dd>
                        {citation?.page
                          ? `${t("Page")} ${citation.page} · `
                          : ""}
                        {citation?.section_id} {t("· Unicode offsets")}{" "}
                        {citation?.start}–{citation?.end}
                      </dd>
                      <dt>{t("Citation validity")}</dt>
                      <dd>{citation?.match_status || "INVALID"}</dd>
                      <dt>{t("Qualifications")}</dt>
                      <dd>
                        {selected.qualifications?.join(" ") ||
                          t(
                            "No additional qualifications recorded; inspect surrounding source context.",
                          )}
                      </dd>
                    </dl>
                    <details>
                      <summary>
                        {t("Verification method & execution metadata")}
                      </summary>
                      <p className="small-copy">
                        {t("Generator:")}
                        {selected.provider} / {selected.model}
                      </p>
                      <pre>
                        {JSON.stringify(selected.verification || {}, null, 2)}
                      </pre>
                      <p className="small-copy muted">
                        {t(
                          "A model verifier is not independent human adjudication. Source matching and semantic interpretation are separate checks.",
                        )}
                      </p>
                    </details>
                    <p className="small-copy muted">
                      {t(
                        "This record supports inspection of the captured document. It does not prove real-world compliance, legal enforceability or admissibility.",
                      )}
                    </p>
                  </section>
                )}
              </aside>
            </div>
          </>
        )}
        <details className="coverage-footer" data-testid="processing-coverage">
          <summary>{t("Processing coverage")}</summary>
          <CoverageNotice coverage={data?.coverage} state={state} />
          {data?.overview && (
            <details>
              <summary>{t("Original analysis overview")}</summary>
              <p>{data.overview.summary}</p>
            </details>
          )}
          <details>
            <summary>{t("Limitations")}</summary>
            {data?.limitations?.map((l) => (
              <p className="small-copy" key={l}>
                {l}
              </p>
            ))}
          </details>
          <details>
            <summary>{t("Provider and model execution metadata")}</summary>
            <pre>{JSON.stringify(data?.model_calls || [], null, 2)}</pre>
          </details>
        </details>
      </div>
    </section>
  );
}
