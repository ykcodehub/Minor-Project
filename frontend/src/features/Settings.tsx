import { useLanguage } from "../app/language";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Download, Save, Trash2 } from "lucide-react";
import { api, download, post } from "../lib/api";
import { useSession } from "../app/session";
import {
  Empty,
  ErrorNotice,
  Loading,
  Notice,
  PageHeading,
} from "../components/ui";
export default function Settings() {
  const { t } = useLanguage();

  const { user, loading, refresh, clear } = useSession();
  const [days, setDays] = useState(30);
  const [provider, setProvider] = useState("gemini");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [saved, setSaved] = useState(false);
  const [confirm, setConfirm] = useState("");
  const navigate = useNavigate();
  useEffect(() => {
    if (user) {
      setDays(user.retention_days);
      setProvider(user.preferred_provider || "gemini");
    }
  }, [user]);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    setSaved(false);
    try {
      await api("/me", {
        method: "PATCH",
        body: JSON.stringify({
          retention_days: days,
          preferred_provider: provider,
        }),
      });
      await refresh();
      setSaved(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function exportData() {
    setError(undefined);
    try {
      await download("/me/export", "veriora-account-data.json");
    } catch (e) {
      setError(e);
    }
  }
  async function remove() {
    setBusy(true);
    setError(undefined);
    try {
      await api("/me", { method: "DELETE" });
      navigate("/sign-in", { replace: true });
      await clear();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (loading) return <Loading />;
  return (
    <section className="page narrow">
      <PageHeading
        eyebrow={t("ACCOUNT & PRIVACY")}
        title={t("Your data, your decisions")}
      >
        {t("Control retention and choose your preferred processing provider.")}
      </PageHeading>
      {!user ? (
        <Empty title={t("Sign in to manage your account")}>
          <Link to="/sign-in" className="text-link">
            {t("Go to sign in")}
          </Link>
        </Empty>
      ) : (
        <>
          <ErrorNotice error={error} />
          {user.guest && (
            <Notice warning>
              {t(
                "This is a temporary guest session. Durable account export requires registration.",
              )}
            </Notice>
          )}
          <form className="panel settings-panel fields" onSubmit={save}>
            <h2>{t("Account & retention")}</h2>
            <button
              type="button"
              className="button secondary"
              disabled={busy || user.guest}
              onClick={async () => {
                setBusy(true);
                setError(undefined);
                try {
                  const result = await post<{ url: string }>(
                    "/auth/google/link",
                  );
                  window.location.assign(result.url);
                } catch (e) {
                  setError(e);
                  setBusy(false);
                }
              }}
            >
              {t("Link verified Google identity")}
            </button>
            <p className="muted">
              {user.guest ? t("Guest session") : user.email}
            </p>
            <label>
              {t("Document retention")}
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              >
                {[1, 7, 14, 30]
                  .filter((d) => !user.guest || d === 1)
                  .map((d) => (
                    <option key={d} value={d}>
                      {d} {d === 1 ? "day" : "days"}
                    </option>
                  ))}
              </select>
            </label>
            <p className="small-copy muted">
              {t(
                "You can delete documents at any time. Retention cleanup removes expired source files and derived content. Backup and provider retention may follow separate policies.",
              )}
            </p>
            <label>
              {t("Preferred AI provider")}
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
              >
                {(user.providers || []).map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name}
                    {p.configured ? ` · ${p.model}` : t(" · not configured")}
                  </option>
                ))}
              </select>
            </label>
            <Notice>
              {t(
                "Each analysis still requires consent. Provider fallback is never silently authorized by this preference.",
              )}
            </Notice>
            <div className="actions">
              <button className="button" disabled={busy || user.guest}>
                <Save size={17} />
                {busy ? t("Saving…") : t("Save preferences")}
              </button>
              {saved && (
                <span role="status" className="success-text">
                  {t("Preferences saved")}
                </span>
              )}
            </div>
          </form>
          <section className="panel settings-panel">
            <h2>{t("Export your account data")}</h2>
            <p className="muted">
              {t(
                "Download your available account and analysis metadata in machine-readable form. Individual reports are available in each analysis.",
              )}
            </p>
            <button
              className="button secondary"
              disabled={user.guest}
              onClick={() => void exportData()}
            >
              <Download size={17} />
              {t("Export account data")}
            </button>
          </section>
          <section className="panel settings-panel danger-zone">
            <h2>{t("Delete account and documents")}</h2>
            <p className="muted">
              {t(
                "Remove your session/account, original sources and derived records. Minimal audit records may remain without source content. This action cannot be undone.",
              )}
            </p>
            <label>
              {t("Type DELETE to confirm")}
              <input
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="off"
              />
            </label>
            <button
              className="button danger"
              disabled={confirm !== "DELETE" || busy}
              onClick={() => void remove()}
            >
              <Trash2 size={17} />
              {t("Delete my account and data")}
            </button>
          </section>
        </>
      )}
    </section>
  );
}
