import { useLanguage } from "../app/language";
import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Send } from "lucide-react";
import { api, post } from "../lib/api";
import type { Citation, Language } from "../lib/types";
import { useSession } from "../app/session";
import { ErrorNotice, Loading } from "../components/ui";

interface Answer {
  answer: string;
  citations?: (Citation & { finding_id?: string })[];
  limitations?: string[];
  question?: string;
  question_id?: string;
}
interface Exchange {
  question: string;
  result: Answer;
}
export default function QuestionPanel({
  analysisId,
  language = "en",
  sourceCount,
  suggestions = [],
  disabled,
  onCitation,
}: {
  analysisId: string;
  language?: Language;
  sourceCount: number;
  suggestions?: string[];
  disabled: boolean;
  onCitation: (c: Citation & { finding_id?: string }) => void;
}) {
  const { t } = useLanguage();

  const { user } = useSession();
  const qc = useQueryClient();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [latest, setLatest] = useState<Exchange>();
  const history = useQuery({
    queryKey: ["questions", analysisId],
    queryFn: () => api<Answer[]>(`/analyses/${analysisId}/questions`),
    enabled: !!user && !user.guest,
  });
  const guest = useQuery({
    queryKey: ["guest-questions", analysisId],
    queryFn: async () => [] as Exchange[],
    enabled: false,
    initialData: [] as Exchange[],
  });
  const exchanges = user?.guest
    ? guest.data
    : [
        ...(history.data || []).map((a) => ({
          question: a.question || "",
          result: a,
        })),
        ...(latest &&
        !history.data?.some(
          (a) =>
            a.question === latest.question && a.answer === latest.result.answer,
        )
          ? [latest]
          : []),
      ];
  async function ask(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const result = await post<Answer>(`/analyses/${analysisId}/questions`, {
        question,
        language,
      });
      setLatest({ question, result });
      if (user?.guest)
        qc.setQueryData<Exchange[]>(["guest-questions", analysisId], (old) => [
          ...(old || []),
          { question, result },
        ]);
      else await history.refetch();
      setQuestion("");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel ask-panel">
      <h2>{t("Ask Veriora")}</h2>
      <p className="muted small-copy">
        {sourceCount}{" "}
        {t("selected document(s). External legal research is not enabled.")}
      </p>
      <ErrorNotice error={error || history.error} />
      {history.isFetching && !user?.guest && (
        <Loading label={t("Loading conversation…")} />
      )}
      {exchanges.map((a, i) => (
        <article className="answer" key={a.result.question_id || i}>
          <h3>{a.question}</h3>
          <p>{a.result.answer}</p>
          {a.result.citations?.map((c, j) => (
            <button
              className="citation-chip"
              key={`${c.section_id}-${j}`}
              onClick={() => onCitation(c)}
            >
              {c.page ? `${t("Page")} ${c.page}` : t("Source passage")}
              <ArrowRight size={15} />
            </button>
          ))}
          {a.result.limitations?.map((l) => (
            <p className="muted small-copy" key={l}>
              {l}
            </p>
          ))}
        </article>
      ))}
      {!exchanges.length && !history.isFetching && suggestions.length > 0 && (
        <div className="suggested-questions">
          {suggestions.map((s) => (
            <button
              className="button secondary small"
              key={s}
              onClick={() => setQuestion(s)}
              disabled={disabled}
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <form onSubmit={ask}>
        <label htmlFor="question">{t("Your document question")}</label>
        <div className="question-input">
          <textarea
            id="question"
            rows={2}
            required
            maxLength={4000}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t("Ask about this document")}
          />
          <button className="button" disabled={busy || disabled}>
            {busy ? t("Checking…") : t("Ask")}
            <Send size={16} />
          </button>
        </div>
      </form>
    </section>
  );
}
