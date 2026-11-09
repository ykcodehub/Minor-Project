import { useLanguage } from "../app/language";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ExternalLink,
  FileText,
  Link2,
  ScanText,
  Upload,
  X,
} from "lucide-react";
import { api, post } from "../lib/api";
import { active, type Discovery, type Job } from "../lib/types";
import { useSession } from "../app/session";
import {
  Empty,
  ErrorNotice,
  Loading,
  Notice,
  PageHeading,
} from "../components/ui";
type Created = { source_id: string; job_id: string };
export default function Intake({
  initialMode = "file",
}: {
  initialMode?: string;
}) {
  const { t } = useLanguage();

  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { user, ensure } = useSession();
  const mode = params.get("mode") || initialMode;
  const [file, setFile] = useState<File>();
  const [text, setText] = useState("");
  const [name, setName] = useState(t("Untitled document"));
  const [url, setUrl] = useState("");
  const [drag, setDrag] = useState(false);
  const [provider, setProvider] = useState(user?.preferred_provider || "");
  const [consent, setConsent] = useState(false);
  const [privacy, setPrivacy] = useState("external");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [stage, setStage] = useState("");
  const [created, setCreated] = useState<Created>();
  const [discoveryId, setDiscoveryId] = useState(params.get("job") || "");
  const [selected, setSelected] = useState<string[]>([]);
  const configured = user?.providers?.filter((p) => p.configured) || [];
  const discovery = useQuery({
    queryKey: ["discovery", discoveryId],
    queryFn: () => api<Discovery>(`/discovery/${discoveryId}`),
    enabled: !!discoveryId,
    refetchInterval: (query) =>
      active(query.state.data?.state || query.state.data?.status)
        ? 1800
        : false,
  });
  const discoveryJob = useQuery({
    queryKey: ["job", discoveryId],
    queryFn: () => api<Job>(`/jobs/${discoveryId}`),
    enabled: !!discoveryId,
    refetchInterval: (query) =>
      active(query.state.data?.state) ? 1500 : false,
  });
  function selectFile(next?: File) {
    setError(undefined);
    if (!next) return;
    if (!/\.(pdf|docx|txt|html?)$/i.test(next.name)) {
      setError(t("Choose a PDF, DOCX, TXT or HTML file."));
      return;
    }
    if (next.size > 20 * 1024 * 1024) {
      setError(t("Files must be 20 MB or smaller."));
      return;
    }
    if (next.size === 0) {
      setError(t("This file is empty."));
      return;
    }
    setFile(next);
  }
  async function waitForJob(id: string) {
    for (let i = 0; i < 180; i++) {
      const job = await api<Job>(`/jobs/${id}`);
      setStage(job.stage || job.state);
      if (!active(job.state)) {
        if (job.state === "FAILED")
          throw Error(
            job.error ||
              t("Document processing failed. Inspect the source and retry."),
          );
        if (["CANCELLED", "CANCELED"].includes(job.state))
          throw Error(t("Processing was canceled."));
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
    throw Error(
      t(
        "Processing is still running. You can reopen the document from your library.",
      ),
    );
  }
  async function analyze(sourceIds: string[]) {
    const me = await ensure();
    const destination =
      provider ||
      me.preferred_provider ||
      me.providers?.find((p) => p.configured)?.name;
    if (
      privacy === "confidential" ||
      !destination ||
      !me.providers?.some((p) => p.name === destination && p.configured)
    ) {
      navigate(`/source/${sourceIds[0]}`);
      return;
    }
    if (!consent)
      throw Error(t("Please authorize the selected provider before analysis."));
    setStage(t("QUEUING ANALYSIS"));
    const a = await post<{ analysis_id: string }>("/analyses", {
      source_ids: sourceIds,
      provider: destination,
      consent: true,
      privacy_mode: privacy,
    });
    navigate(`/analysis/${a.analysis_id}`);
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await ensure();
      if (mode === "url") {
        setStage("DISCOVERING");
        const result = await post<{ job_id: string }>("/discovery", { url });
        setDiscoveryId(result.job_id);
        setParams({ mode: "url", job: result.job_id });
      } else {
        let source = created;
        if (!source) {
          setStage("RECEIVING");
          if (mode === "text") {
            source = await post<Created>("/sources/text", { name, text });
          } else {
            if (!file) throw Error(t("Choose a document first."));
            const body = new FormData();
            body.append("file", file);
            source = await api<Created>("/sources/upload", {
              method: "POST",
              body,
            });
          }
          setCreated(source);
        }
        await waitForJob(source.job_id);
        await analyze([source.source_id]);
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function analyzeSelected() {
    setBusy(true);
    setError(undefined);
    try {
      const sources: string[] = [];
      for (const candidate of selected) {
        setStage(t("FETCHING SELECTED POLICY"));
        const s = await post<Created>("/sources/url", {
          discovery_job_id: discoveryId,
          url: candidate,
        });
        await waitForJob(s.job_id);
        sources.push(s.source_id);
      }
      await analyze(sources);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="page intake-page">
      <PageHeading
        eyebrow={t("START WITH THE SOURCE")}
        title={t("What would you like to analyze?")}
      >
        {t("Bring a document. Keep the context. Get back to the exact words.")}
      </PageHeading>
      <div className="intake-layout">
        <div>
          <div className="panel intake-panel">
            <div
              className="tabs"
              role="tablist"
              aria-label={t("Document input method")}
            >
              {[
                { id: "file", title: t("Upload file"), Icon: Upload },
                { id: "text", title: t("Paste text"), Icon: ScanText },
                { id: "url", title: t("Website URL"), Icon: Link2 },
              ].map(({ id, title, Icon }) => (
                <button
                  role="tab"
                  aria-selected={mode === id}
                  key={id}
                  disabled={busy}
                  onClick={() => {
                    setParams({ mode: id });
                    setCreated(undefined);
                    setError(undefined);
                  }}
                >
                  <Icon size={17} />
                  {title}
                </button>
              ))}
            </div>
            <form onSubmit={submit}>
              {mode === "file" && (
                <>
                  <div
                    className={`dropzone ${drag ? "drag" : ""}`}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDrag(true);
                    }}
                    onDragLeave={() => setDrag(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDrag(false);
                      selectFile(e.dataTransfer.files[0]);
                      setCreated(undefined);
                    }}
                  >
                    <span className="upload-symbol">
                      <Upload size={28} />
                    </span>
                    <h2>{t("Drop your document here")}</h2>
                    <p>{t("or choose a file from your device")}</p>
                    <label className="button secondary file-label">
                      {t("Choose file")}
                      <input
                        aria-label={t("Choose document file")}
                        type="file"
                        accept=".pdf,.docx,.txt,.html,.htm"
                        disabled={busy}
                        onChange={(e) => {
                          selectFile(e.target.files?.[0]);
                          setCreated(undefined);
                        }}
                      />
                    </label>
                    <small>
                      {t(
                        "PDF, DOCX, TXT, HTML · Up to 20 MB · Up to 150 pages",
                      )}
                    </small>
                  </div>
                  {file && (
                    <div className="file-selected">
                      <FileText size={22} />
                      <div>
                        <strong>{file.name}</strong>
                        <span className="muted">
                          {(file.size / 1024).toFixed(1)} {t("KB")}
                        </span>
                      </div>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={t("Remove file")}
                        onClick={() => {
                          setFile(undefined);
                          setCreated(undefined);
                        }}
                        disabled={busy}
                      >
                        <X size={18} />
                      </button>
                    </div>
                  )}
                </>
              )}
              {mode === "text" && (
                <div className="fields">
                  <label>
                    {t("Document name")}
                    <input
                      maxLength={200}
                      required
                      value={name}
                      onChange={(e) => {
                        setName(e.target.value);
                        setCreated(undefined);
                      }}
                    />
                  </label>
                  <label>
                    {t("Original document text")}
                    <textarea
                      required
                      rows={11}
                      minLength={1}
                      value={text}
                      onChange={(e) => {
                        setText(e.target.value);
                        setCreated(undefined);
                      }}
                      placeholder={t(
                        "Paste the complete agreement or the passage you want to inspect.",
                      )}
                    />
                  </label>
                  <small className="muted">
                    {text.length.toLocaleString()}{" "}
                    {t(
                      "characters · Exact submitted text is retained as your source.",
                    )}
                  </small>
                </div>
              )}
              {mode === "url" && (
                <div className="fields">
                  <div className="url-illustration">
                    <Link2 size={30} />
                  </div>
                  <h2>{t("Find the policies behind a website.")}</h2>
                  <p className="muted">
                    {t(
                      "Review accessible official legal pages before choosing what to analyze.",
                    )}
                  </p>
                  <label>
                    {t("Official website URL")}
                    <input
                      type="url"
                      required
                      placeholder={"https://example.com"}
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                    />
                  </label>
                  <Notice>
                    {t(
                      "Discovery checks accessible links. Other terms may exist, and protected pages will not be bypassed.",
                    )}
                  </Notice>
                </div>
              )}
              <ErrorNotice error={error} />
              {busy && (
                <Loading
                  label={
                    stage.replaceAll("_", " ").toLowerCase() ||
                    t("Processing your source…")
                  }
                />
              )}
              <div className="form-footer">
                <span className="muted">
                  {mode === "url"
                    ? t("Select sources after discovery.")
                    : t(
                        "Original source and acquisition metadata are preserved.",
                      )}
                </span>
                <button
                  className="button"
                  type="submit"
                  disabled={busy || (mode === "file" && !file)}
                >
                  {mode === "url"
                    ? t("Find legal documents")
                    : configured.length && privacy === "external"
                      ? t("Upload & analyze")
                      : t("Save & inspect source")}
                  <ArrowRight size={17} />
                </button>
              </div>
            </form>
          </div>
          {discoveryId && (
            <div className="panel discovery-panel">
              <h2>{t("Discovered policy candidates")}</h2>
              <ErrorNotice error={discovery.error || discoveryJob.error} />
              {discoveryJob.data?.state === "FAILED" && (
                <ErrorNotice
                  error={
                    discoveryJob.data.error ||
                    t("Policy discovery failed. Check the URL and try again.")
                  }
                />
              )}
              {active(discoveryJob.data?.state) && (
                <Loading
                  label={`Discovery: ${discoveryJob.data?.stage || "queued"}`}
                />
              )}
              <Notice>
                {t(
                  "These pages were linked from the website. Discovery is not a completeness guarantee.",
                )}
              </Notice>
              {discovery.data?.candidates?.length
                ? discovery.data.candidates.map((c) => (
                    <label className="candidate" key={c.url}>
                      <input
                        type="checkbox"
                        disabled={
                          ![
                            "AVAILABLE",
                            "accessible",
                            "available",
                            "COMPLETED",
                            "ok",
                          ].includes(c.status)
                        }
                        checked={selected.includes(c.url)}
                        onChange={(e) =>
                          setSelected((s) =>
                            e.target.checked
                              ? [...s, c.url]
                              : s.filter((x) => x !== c.url),
                          )
                        }
                      />
                      <div>
                        <strong>
                          {c.title ||
                            c.type ||
                            c.kind ||
                            c.category ||
                            t("Legal policy")}
                        </strong>
                        <a
                          href={c.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {c.url}
                          <ExternalLink size={13} />
                        </a>
                        <small>
                          {c.status}
                          {c.discovered_from &&
                            ` · Linked from ${c.discovered_from}`}
                        </small>
                        {(c.error || c.reason) && (
                          <span className="muted">{c.error || c.reason}</span>
                        )}
                      </div>
                    </label>
                  ))
                : !active(discoveryJob.data?.state) && (
                    <Empty title={t("No accessible candidates yet")}>
                      {t("Try another official starting page.")}
                    </Empty>
                  )}
              {(discovery.data?.missing_categories || discovery.data?.missing)
                ?.length ? (
                <p className="muted">
                  {t("Not found or inaccessible:")}{" "}
                  {(
                    discovery.data.missing_categories ||
                    discovery.data.missing ||
                    []
                  ).join(", ")}
                </p>
              ) : null}
              {discovery.data?.warnings?.map((w) => (
                <p key={w} className="muted">
                  {w}
                </p>
              ))}
              <button
                className="button"
                disabled={busy || !selected.length}
                onClick={() => void analyzeSelected()}
              >
                {t("Analyze")}
                {selected.length || ""} {t("selected")}{" "}
                {selected.length === 1 ? "document" : "documents"}
                <ArrowRight size={17} />
              </button>
            </div>
          )}
        </div>
        <aside className="intake-aside">
          <div className="panel">
            <p className="eyebrow">{t("PROCESSING & PRIVACY")}</p>
            <h3>{t("You choose where the text goes.")}</h3>
            <label>
              {t("Processing mode")}
              <select
                value={privacy}
                onChange={(e) => setPrivacy(e.target.value)}
              >
                <option value="external">{t("External AI provider")}</option>
                <option value="confidential">
                  {t("Confidential · source inspection only")}
                </option>
              </select>
            </label>
            {privacy === "external" ? (
              <>
                <label>
                  {t("AI provider")}
                  <select
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                  >
                    <option value="">
                      {configured.length
                        ? t("Choose configured provider")
                        : t("No provider configured")}
                    </option>
                    {configured.map((p) => (
                      <option key={p.name} value={p.name}>
                        {p.name} · {p.model}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="muted small-copy">
                  {t(
                    "Your document text will be sent to the selected provider for interpretation and verification. Provider retention and processing terms apply.",
                  )}
                </p>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                  />
                  {t(
                    "I authorize this document to be processed by the selected AI provider.",
                  )}
                </label>
                {!configured.length && (
                  <Notice warning>
                    {t(
                      "Source inspection works without AI credentials. An administrator must configure a provider to enable analysis.",
                    )}
                  </Notice>
                )}
              </>
            ) : (
              <Notice>
                {t(
                  "External AI transfer is blocked. You can preserve and inspect extracted text; confidential AI processing is not configured.",
                )}
              </Notice>
            )}
          </div>
          <div className="aside-note">
            <h3>{t("A source, not a promise.")}</h3>
            <p>
              {t(
                "Findings explain what a document says. They do not establish legal enforceability or what an organization does in practice.",
              )}
            </p>
            <Link to="/#verification" className="text-link">
              {t("About verification")}
              <ArrowRight size={15} />
            </Link>
          </div>
        </aside>
      </div>
    </section>
  );
}
