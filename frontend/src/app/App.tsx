import { lazy, Suspense, useState, type ReactNode } from "react";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useNavigate,
  Navigate,
} from "react-router-dom";
import { ArrowUpRight, LogOut, Settings2, Globe2 } from "lucide-react";
import { BrandMark } from "../components/BrandMark";
import { useLanguage } from "./language";
import { useSession } from "./session";
import { post, ApiError } from "../lib/api";
import { ErrorNotice, Loading } from "../components/ui";
const Landing = lazy(() => import("../features/Landing"));
const Intake = lazy(() => import("../features/Intake"));
const Auth = lazy(() => import("../features/Auth"));
const Library = lazy(() => import("../features/Library"));
const Dashboard = lazy(() => import("../features/Dashboard"));
const Settings = lazy(() => import("../features/Settings"));
const Workspace = lazy(() => import("../features/Workspace"));
const Compare = lazy(() => import("../features/Compare"));
const SourcePage = lazy(() => import("../features/SourcePage"));
function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useSession();
  if (loading) return <Loading />;
  return user ? children : <Navigate to="/sign-in" replace />;
}
export default function App() {
  const { language, setLanguage, t } = useLanguage();
  const [languageOpen, setLanguageOpen] = useState(false);
  const { user, clear } = useSession();
  const navigate = useNavigate();
  const [authError, setAuthError] = useState<unknown>();
  const [signingOut, setSigningOut] = useState(false);
  async function logout() {
    setSigningOut(true);
    setAuthError(undefined);
    try {
      try {
        await post("/auth/logout");
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 401)) throw error;
        // An already-expired server session still needs local identity/cache cleanup.
      }
      navigate("/sign-in", { replace: true });
      await clear();
    } catch (error) {
      setAuthError(error);
    } finally {
      setSigningOut(false);
    }
  }
  return (
    <>
      <a className="skip" href="#main">
        {t("Skip to content")}
      </a>
      <header className="topbar">
        <Link className="brand" to="/" aria-label={t("Veriora home")}>
          <BrandMark />
          {"veriora"}
        </Link>
        <nav aria-label={t("Main navigation")}>
          <NavLink to="/dashboard">{t("Dashboard")}</NavLink>
          <NavLink to="/analyze">{t("Analyze")}</NavLink>
          <NavLink to="/library">{t("Library")}</NavLink>
        </nav>
        <div className="account-nav">
          <div
            className="global-language"
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setLanguageOpen(false);
                e.currentTarget.querySelector("button")?.focus();
              }
            }}
          >
            <button
              className="icon-button"
              data-testid="global-language-toggle"
              aria-label={t("Language")}
              aria-expanded={languageOpen}
              onClick={() => setLanguageOpen(!languageOpen)}
            >
              <Globe2 size={19} />
              <span className="language-code">
                {language === "hi"
                  ? "हिं"
                  : language === "hinglish"
                    ? "HI/EN"
                    : "EN"}
              </span>
            </button>
            {languageOpen && (
              <div className="language-popover">
                <label>
                  {t("Application language")}
                  <select
                    data-testid="global-language-select"
                    aria-label={t("Application language")}
                    value={language}
                    onChange={(e) => {
                      void setLanguage(e.target.value as typeof language).catch(
                        setAuthError,
                      );
                      setLanguageOpen(false);
                    }}
                  >
                    <option value="en">{"English"}</option>
                    <option value="hi">हिन्दी</option>
                    <option value="hinglish">{"Hinglish"}</option>
                  </select>
                </label>
              </div>
            )}
          </div>
          {user ? (
            <>
              <Link className="account" to="/settings">
                <Settings2 size={17} />
                <span>{user.guest ? t("Guest session") : t("Account")}</span>
              </Link>
              <button
                className="icon-button"
                title={t("Sign out")}
                aria-label={t("Sign out")}
                disabled={signingOut}
                onClick={() => void logout()}
              >
                <LogOut size={17} />
              </button>
              {user.guest && (
                <Link className="button small" to="/sign-in">
                  {t("Save your work")}
                  <ArrowUpRight size={15} />
                </Link>
              )}
            </>
          ) : (
            <Link className="button secondary small" to="/sign-in">
              {t("Sign in")}
              <ArrowUpRight size={15} />
            </Link>
          )}
        </div>
      </header>
      <main id="main">
        <ErrorNotice error={authError} />
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/analyze" element={<Intake />} />
            <Route path="/discover" element={<Intake initialMode="url" />} />
            <Route path="/sign-in" element={<Auth />} />
            <Route path="/register" element={<Auth key="register" />} />
            <Route path="/verify-email" element={<Auth key="verify" />} />
            <Route path="/forgot-password" element={<Auth key="recover" />} />
            <Route path="/reset-password" element={<Auth key="reset" />} />
            <Route
              path="/compare"
              element={
                <Protected>
                  <Compare />
                </Protected>
              }
            />
            <Route
              path="/library"
              element={
                <Protected>
                  <Library />
                </Protected>
              }
            />
            <Route
              path="/dashboard"
              element={
                <Protected>
                  <Dashboard />
                </Protected>
              }
            />
            <Route
              path="/settings"
              element={
                <Protected>
                  <Settings />
                </Protected>
              }
            />
            <Route
              path="/analysis/:id"
              element={
                <Protected>
                  <Workspace />
                </Protected>
              }
            />
            <Route
              path="/source/:id"
              element={
                <Protected>
                  <SourcePage />
                </Protected>
              }
            />
            <Route
              path="*"
              element={
                <section className="page narrow">
                  <h1>{t("Page not found")}</h1>
                  <p>{t("This address is unavailable.")}</p>
                  <Link className="button" to="/analyze">
                    {t("Analyze a document")}
                  </Link>
                </section>
              }
            />
          </Routes>
        </Suspense>
      </main>
      <footer className="footer">
        <Link className="brand" to="/">
          {"veriora"}
        </Link>
        <span>
          © {new Date().getFullYear()} Veriora · {t("All rights reserved.")}
        </span>
        <span>
          {t("Interpretations inform your review. They are not legal advice.")}
        </span>
      </footer>
    </>
  );
}
