import {
  createContext,
  useContext,
  useEffect,
  useState,
  useRef,
  useCallback,
} from "react";
import { useSession } from "./session";
import { api } from "../lib/api";
import type { Language, User } from "../lib/types";
import catalog from "../lib/messages.json";

const valid = (value: string | null | undefined): Language =>
  value === "hi" || value === "hinglish" ? value : "en";
const canonical = new Map(
  Object.entries(catalog).flatMap(([key, messages]) =>
    Object.values(messages).map((value) => [value, key] as const),
  ),
);
const LanguageContext = createContext({
  language: "en" as Language,
  t: (key: string) => key,
  setLanguage: async (value: Language) => {
    void value;
  },
});
export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const { user } = useSession();
  const [choice, setChoice] = useState<Language>(() =>
    valid(localStorage.getItem("veriora-language")),
  );
  const [pending, setPending] = useState<Language>();
  const owner = useRef<string | undefined>(undefined);
  const writes = useRef<Promise<unknown>>(Promise.resolve());
  const latest = useRef<Language | undefined>(undefined);
  const language = pending || (user ? valid(user.language) : choice);
  useEffect(() => {
    if (owner.current !== user?.id) {
      owner.current = user?.id;
      if (user?.is_guest && choice !== user.language) {
        setPending(choice);
        writes.current = writes.current
          .catch(() => {})
          .then(() =>
            api("/me/language", {
              method: "PATCH",
              body: JSON.stringify({ language: choice }),
            }),
          )
          .catch(() => {});
      } else setPending(undefined);
    }
  }, [user?.id, user?.is_guest, user?.language, choice]);
  useEffect(() => {
    document.documentElement.lang =
      language === "hi" ? "hi" : language === "hinglish" ? "hi-Latn" : "en";
    localStorage.setItem("veriora-language", language);
  }, [language]);
  const t = useCallback(
    (key: string) => {
      const original = canonical.get(key) || key;
      return language === "en"
        ? original
        : (catalog as Record<string, Record<string, string>>)[original]?.[
            language
          ] || key;
    },
    [language],
  );
  async function setLanguage(next: Language) {
    const previous = language;
    const userId = user?.id;
    latest.current = next;
    setChoice(next);
    setPending(next);
    if (userId) {
      const operation = writes.current
        .catch(() => {})
        .then(async () => {
          if (owner.current !== userId)
            throw Error("Session changed. Please select your language again.");
          await api<User>("/me/language", {
            method: "PATCH",
            body: JSON.stringify({ language: next }),
          });
        });
      writes.current = operation;
      try {
        await operation;
      } catch (e) {
        if (latest.current === next) {
          setChoice(previous);
          setPending(previous);
        }
        throw e;
      }
    }
  }

  return (
    <LanguageContext.Provider value={{ language, t, setLanguage }}>
      {children}
    </LanguageContext.Provider>
  );
}
export const useLanguage = () => useContext(LanguageContext);
