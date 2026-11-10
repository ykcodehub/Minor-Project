import { useLanguage } from "../app/language";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useProcessingPoll } from "../lib/useProcessingPoll";
import { api, post } from "../lib/api";
import type { Source } from "../lib/types";
import { useSession } from "../app/session";
import { CoverageNotice } from "../components/CoverageNotice";
import { SourceViewer } from "../components/SourceViewer";
import {
  ErrorNotice,
  Loading,
  Notice,
  PageHeading,
  ProcessingPaused,
  Status,
} from "../components/ui";
export default function SourcePage() {
  const { t } = useLanguage();

  const { id = "" } = useParams();
  const polling = useProcessingPoll(id);
  const { user } = useSession();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [provider, setProvider] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const query = useQuery({
    queryKey: ["source", id],
    queryFn: () => api<Source>(`/sources/${id}`),
    refetchInterval: (q) =>
      !polling.paused &&
      !q.state.error &&
      ["QUEUED", "PROCESSING"].includes(q.state.data?.status || "")
        ? 2000
        : false,
  });
  async function analyze() {
    setBusy(true);
    setError(undefined);
    try {
      const result = await post<{ analysis_id: string }>("/analyses", {
        source_ids: [id],
        provider:
          user?.authorized_providers != null
            ? user.preferred_provider
            : provider,
        consent: user?.authorized_providers != null || consent,
        privacy_mode: "external",
      });
      navigate(`/analysis/${result.analysis_id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (query.isPending) return <Loading />;
  if (query.error)
    return (
      <section className="page">
        <ErrorNotice error={query.error} />
        <Link to="/library">{t("Back to library")}</Link>
      </section>
    );
  const source = query.data!;
  return (
    <section className="page">
      <PageHeading
        eyebrow={t("CAPTURED SOURCE")}
        title={source.original_name}
        actions={
          <Link className="button secondary" to="/library">
            {t("Back to library")}
          </Link>
        }
      >
        {t("Preserved original source, separate from AI interpretation.")}
      </PageHeading>
      {polling.paused && ["QUEUED", "PROCESSING"].includes(source.status) && (
        <ProcessingPaused
          onResume={() => {
            polling.resume();
            void query.refetch();
          }}
        />
      )}
      <ErrorNotice error={error} />
      <ErrorNotice error={source.processing_error} />
      {["FAILED", "CANCELLED"].includes(source.job_state || "") &&
        source.job_id && (
          <div className="notice">
            <p>
              {t(
                "Extraction did not complete. You can retry the preserved source or upload a corrected copy.",
              )}
            </p>
            <button
              className="button secondary"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError(undefined);
                try {
                  await post(`/jobs/${source.job_id}/retry`);
                  polling.resume();
                  await qc.invalidateQueries({ queryKey: ["source", id] });
                } catch (e) {
                  setError(e);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {t("Retry extraction")}
            </button>
          </div>
        )}
      {source.warnings?.map((w) => (
        <Notice warning key={w}>
          {w}
        </Notice>
      ))}
      <CoverageNotice coverage={source.coverage} extraction />
      <div className="source-detail-layout">
        <div className="panel">
          <SourceViewer sourceId={id} />
        </div>
        <aside>
          <section className="panel passport">
            <h2>{t("Source provenance")}</h2>
            <Status value={source.status} />
            <dl>
              <dt>{t("Captured")}</dt>
              <dd>{new Date(source.captured_at).toLocaleString()}</dd>
              <dt>{t("Source identifier / version")}</dt>
              <dd className="mono">{source.id}</dd>
              <dt>{t("SHA-256 of original bytes")}</dt>
              <dd className="mono">{source.sha256}</dd>
              <dt>{t("Original source")}</dt>
              <dd>{source.source_url || t("Uploaded file or pasted text")}</dd>
            </dl>
            <Notice>
              {t(
                "A hash identifies these captured bytes. It does not prove remote origin, conduct, or legal admissibility.",
              )}
            </Notice>
          </section>
          <section className="panel passport">
            <h2>{t("Analyze this source")}</h2>
            <p className="muted">
              {t(
                "External interpretation requires a configured provider and your consent.",
              )}
            </p>
            {user?.authorized_providers != null ? (
              <Notice>
                {t("Saved provider permissions apply automatically.")}{" "}
                {user.authorized_providers.join(", ") ||
                  t("No providers authorized")}
                . <Link to="/settings">{t("Manage provider permissions")}</Link>
              </Notice>
            ) : (
              <>
                <label>
                  {t("AI provider")}
                  <select
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                  >
                    <option value="">{t("Choose configured provider")}</option>
                    {user?.providers
                      ?.filter((p) => p.configured)
                      .map((p) => (
                        <option key={p.name} value={p.name}>
                          {p.name} · {p.model}
                        </option>
                      ))}
                  </select>
                </label>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                  />
                  {t(
                    "I authorize sending this document text to the selected provider. Its processing and retention terms apply.",
                  )}
                </label>
                <Link to="/settings">
                  {t("Save provider permissions once in Settings")}
                </Link>
              </>
            )}
            <button
              className="button"
              disabled={
                (user?.authorized_providers != null
                  ? !user.authorized_providers.length
                  : !provider || !consent) ||
                busy ||
                !source.sections?.length
              }
              onClick={() => void analyze()}
            >
              {busy ? t("Starting…") : t("Analyze document")}
              <ArrowRight size={16} />
            </button>
            {!user?.providers?.some((p) => p.configured) && (
              <Notice warning>
                {t(
                  "AI analysis is unavailable until an administrator configures a provider. No analysis has been generated.",
                )}
              </Notice>
            )}
          </section>
        </aside>
      </div>
    </section>
  );
}
