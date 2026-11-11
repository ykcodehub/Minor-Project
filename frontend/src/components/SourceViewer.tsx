import { useLanguage } from "../app/language";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Minus,
  Plus,
} from "lucide-react";
import { api, download } from "../lib/api";
import { useQuery } from "@tanstack/react-query";
import type { Citation, Source } from "../lib/types";
import { citationValid, splitPassage } from "../lib/evidence";
import { Empty, ErrorNotice, Loading } from "./ui";
export function SourceViewer({
  sourceId,
  citation,
}: {
  sourceId: string;
  citation?: Citation;
}) {
  const { t } = useLanguage();

  const query = useQuery({
    queryKey: ["source", sourceId],
    queryFn: () => api<Source>(`/sources/${sourceId}`),
    enabled: !!sourceId,
  });
  const [zoom, setZoom] = useState(100);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<unknown>();
  const highlight = useRef<HTMLElement>(null);
  const sections = useMemo(
    () => query.data?.sections || [],
    [query.data?.sections],
  );
  const pages = useMemo(() => {
    const groups = new Map<string, typeof sections>();
    for (const section of sections) {
      const key = section.page != null ? `page-${section.page}` : section.id;
      groups.set(key, [...(groups.get(key) || []), section]);
    }
    return [...groups.values()];
  }, [sections]);
  useEffect(() => {
    setIndex(0);
  }, [sourceId]);
  useEffect(() => {
    if (citation) {
      const found = pages.findIndex((group) =>
        group.some((s) => s.id === citation.section_id),
      );
      if (found >= 0) setIndex(found);
    }
  }, [citation, pages]);
  useEffect(() => {
    highlight.current?.scrollIntoView({
      block: "nearest",
      behavior: "instant",
    });
  }, [citation, index]);
  const visible = pages[index] || [];
  const section = visible[0];
  const pageTotal =
    Number(query.data?.coverage?.pages_total || 0) || pages.length;
  async function original() {
    setError(undefined);
    try {
      await download(
        `/sources/${sourceId}/original`,
        query.data?.original_name || "source",
      );
    } catch (e) {
      setError(e);
    }
  }
  return (
    <section className="source-viewer">
      <div className="viewer-heading">
        <div>
          <span className="tiny-label">{t("ORIGINAL SOURCE")}</span>
          <h3>
            <FileText size={17} />
            {query.data?.original_name || t("Document source")}
          </h3>
        </div>
        {query.data?.kind !== "url" && (
          <button
            className="icon-button"
            onClick={() => void original()}
            aria-label={t("Download original source")}
            title={t("Download original source")}
          >
            <Download size={17} />
          </button>
        )}
      </div>
      <div className="viewer-toolbar">
        <div className="row">
          <button
            aria-label={t("Previous source section")}
            className="icon-button"
            disabled={index === 0}
            onClick={() => setIndex((i) => i - 1)}
          >
            <ChevronLeft size={17} />
          </button>
          <span>
            {section?.page
              ? `${t("Page")} ${section.page}`
              : `${t("Source section")} ${pages.length ? index + 1 : 0}`}{" "}
            <span className="muted">
              / {section?.page != null ? pageTotal : pages.length}
            </span>
          </span>
          <button
            aria-label={t("Next source section")}
            className="icon-button"
            disabled={index >= pages.length - 1}
            onClick={() => setIndex((i) => i + 1)}
          >
            <ChevronRight size={17} />
          </button>
        </div>
        <div className="row">
          <button
            className="icon-button"
            aria-label={t("Decrease source font size")}
            disabled={zoom <= 80}
            onClick={() => setZoom((z) => z - 10)}
          >
            <Minus size={15} />
          </button>
          <span>{zoom}%</span>
          <button
            className="icon-button"
            aria-label={t("Increase source font size")}
            disabled={zoom >= 200}
            onClick={() => setZoom((z) => z + 10)}
          >
            <Plus size={15} />
          </button>
        </div>
      </div>
      <ErrorNotice error={query.error || error} />
      {query.isPending ? (
        <Loading label={t("Loading captured source…")} />
      ) : section ? (
        <div className="source-paper" style={{ fontSize: `${zoom}%` }}>
          <p className="source-location">
            {section.heading ||
              `Extracted ${section.page ? `page ${section.page}` : `section ${section.ordinal + 1}`}`}
          </p>
          {visible.map((block) => {
            const mapped =
              citation &&
              block.id === citation.section_id &&
              citationValid(citation)
                ? splitPassage(block.text, citation.start, citation.end)
                : null;
            const span =
              mapped && mapped[1] === citation?.quote ? mapped : null;
            return (
              <div
                className="source-text source-block"
                key={block.id}
                data-section-id={block.id}
              >
                {span ? (
                  <>
                    {span[0]}
                    <mark ref={highlight} tabIndex={-1}>
                      {span[1]}
                    </mark>
                    {span[2]}
                  </>
                ) : (
                  block.text
                )}
              </div>
            );
          })}
          <p className="source-extraction-note">
            {t(
              "Extracted source text. Original file layout may differ; locations refer to the captured extraction.",
            )}
          </p>
        </div>
      ) : (
        <Empty title={t("Source text is not available")}>
          {t(
            "Extraction may still be running, or this document may require OCR.",
          )}
        </Empty>
      )}
    </section>
  );
}
