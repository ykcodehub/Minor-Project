import { useLanguage } from "../app/language";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  FileText,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { api, apiPage } from "../lib/api";
import type { Source } from "../lib/types";
import { Pagination } from "../components/Pagination";
import { useSession } from "../app/session";
import {
  ConfirmDialog,
  Empty,
  ErrorNotice,
  Loading,
  Notice,
  PageHeading,
  Status,
} from "../components/ui";
export default function Library() {
  const { t } = useLanguage();

  const { user, loading } = useSession();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [pendingDelete, setPendingDelete] = useState<Source>();
  const [renaming, setRenaming] = useState<Source>();
  const [title, setTitle] = useState("");
  const [renameError, setRenameError] = useState<unknown>();
  const rename = useMutation({
    mutationFn: () =>
      api(`/sources/${renaming?.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: title }),
      }),
    onSuccess: () => {
      setRenaming(undefined);
      void qc.invalidateQueries({ queryKey: ["sources"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: setRenameError,
  });
  const [sort, setSort] = useState("captured_desc");
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: ["sources", search, sort, offset],
    queryFn: () =>
      apiPage<Source>(
        `/sources?${new URLSearchParams({ q: search, sort, offset: String(offset), limit: "30" })}`,
      ),
    enabled: !!user,
    refetchInterval: 10000,
  });
  const deletion = useMutation({
    mutationFn: (id: string) => api(`/sources/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setPendingDelete(undefined);
      void qc.invalidateQueries({ queryKey: ["sources"] });
    },
  });
  const sources = query.data?.items || [];
  if (loading) return <Loading />;
  return (
    <section className="page">
      <PageHeading
        eyebrow={t("YOUR DOCUMENT WORKSPACE")}
        title={t("Document library")}
        actions={
          <>
            <Link className="button secondary" to="/compare">
              {t("Compare sources")}
            </Link>
            <Link className="button" to="/analyze">
              <Plus size={17} />
              {t("New analysis")}
            </Link>
          </>
        }
      >
        {t(
          "Your sources, their analyses, and the evidence that connects them.",
        )}
      </PageHeading>
      {!user ? (
        <div className="panel">
          <Empty title={t("Your documents belong here")}>
            {t(
              "Sign in for a saved library, or start with a limited guest session.",
            )}
          </Empty>
          <div className="center actions">
            <Link to="/sign-in" className="button">
              {t("Sign in")}
            </Link>
            <Link to="/analyze" className="button secondary">
              {t("Analyze as a guest")}
            </Link>
          </div>
        </div>
      ) : (
        <>
          {user.guest && (
            <Notice warning>
              {t("Guest documents are temporary.")}{" "}
              <Link to="/sign-in">{t("Create an account")}</Link>{" "}
              {t(
                "for a persistent library and report exports. Creating an account in this session preserves your current guest documents.",
              )}
            </Notice>
          )}
          <div className="library-tools">
            <label className="search-field">
              <Search size={17} />
              <span className="sr-only">{t("Search documents")}</span>
              <input
                placeholder={t("Search your documents")}
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setOffset(0);
                }}
              />
            </label>
            <label className="inline-label">
              {t("Sort by")}
              <select
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="captured_desc">{t("Newest first")}</option>
                <option value="name_asc">{t("Document name")}</option>
              </select>
            </label>
          </div>
          <ErrorNotice error={query.error} />
          {query.isPending ? (
            <Loading />
          ) : sources.length ? (
            <div className="panel library-table">
              <div className="library-table-head">
                <span>{t("DOCUMENT")}</span>
                <span>{t("CAPTURED")}</span>
                <span>{t("STATE")}</span>
                <span>{t("ACTIONS")}</span>
              </div>
              {sources.map((source) => (
                <article className="library-row" key={source.id}>
                  <div className="document-cell">
                    <span className="document-icon">
                      <FileText size={22} />
                    </span>
                    <div>
                      <Link
                        className="document-name"
                        to={
                          source.analysis_id
                            ? `/analysis/${source.analysis_id}`
                            : `/source/${source.id}`
                        }
                      >
                        {source.original_name}
                      </Link>
                      <small>
                        {source.kind} · {source.sha256?.slice(0, 12)}…
                      </small>
                    </div>
                  </div>
                  <time dateTime={source.captured_at}>
                    {new Date(source.captured_at).toLocaleDateString()}
                  </time>
                  <Status value={source.analysis_status || source.status} />
                  <div className="actions">
                    <button
                      className="icon-button"
                      aria-label={`Rename ${source.original_name}`}
                      onClick={() => {
                        setRenaming(source);
                        setTitle(source.original_name);
                        setRenameError(undefined);
                      }}
                    >
                      <Pencil size={17} />
                    </button>
                    <Link
                      className="icon-button"
                      title={t("Open document")}
                      aria-label={`Open ${source.original_name}`}
                      to={
                        source.analysis_id
                          ? `/analysis/${source.analysis_id}`
                          : `/source/${source.id}`
                      }
                    >
                      <ArrowUpRight size={19} />
                    </Link>
                    <button
                      className="icon-button danger-text"
                      title={t("Delete document")}
                      aria-label={`Delete ${source.original_name}`}
                      onClick={() => setPendingDelete(source)}
                    >
                      <Trash2 size={17} />
                    </button>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="panel">
              <Empty
                title={
                  search
                    ? t("No matching documents")
                    : t("Your next document starts here")
                }
              >
                {search
                  ? t("Try another name.")
                  : t(
                      "Upload an agreement or discover a website’s policies to begin your review.",
                    )}
              </Empty>
            </div>
          )}
          <Pagination
            offset={offset}
            total={query.data?.total ?? null}
            count={sources.length}
            pageSize={30}
            onChange={setOffset}
          />
        </>
      )}
      {renaming && (
        <ConfirmDialog
          titleId="rename-title"
          onClose={() => setRenaming(undefined)}
        >
          <h2 id="rename-title">{t("Rename document")}</h2>
          <p>
            {t(
              "The display name changes. Original bytes, source version and hash stay preserved.",
            )}
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              rename.mutate();
            }}
          >
            <label>
              {t("Document display name")}
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                maxLength={255}
              />
            </label>
            <ErrorNotice error={renameError} />
            <div className="actions">
              <button
                type="button"
                className="button secondary"
                onClick={() => setRenaming(undefined)}
              >
                {t("Cancel")}
              </button>
              <button
                className="button"
                disabled={rename.isPending || !title.trim()}
              >
                {t("Save name")}
              </button>
            </div>
          </form>
        </ConfirmDialog>
      )}
      {pendingDelete && (
        <ConfirmDialog
          titleId="delete-title"
          onClose={() => setPendingDelete(undefined)}
        >
          <h2 id="delete-title">{t("Delete this document?")}</h2>
          <p>
            “{pendingDelete.original_name}
            {t(
              "”, its extracted text, analyses and derived records will be removed. This cannot be undone. Minimal audit records may remain without document text.",
            )}
          </p>
          <ErrorNotice error={deletion.error} />
          <div className="actions">
            <button
              autoFocus
              className="button secondary"
              disabled={deletion.isPending}
              onClick={() => setPendingDelete(undefined)}
            >
              {t("Keep document")}
            </button>
            <button
              className="button danger"
              disabled={deletion.isPending}
              onClick={() => deletion.mutate(pendingDelete.id)}
            >
              {deletion.isPending ? t("Deleting…") : t("Delete document")}
            </button>
          </div>
        </ConfirmDialog>
      )}
    </section>
  );
}
