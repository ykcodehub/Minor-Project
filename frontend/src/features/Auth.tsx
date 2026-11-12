import { useLanguage } from "../app/language";
import { useEffect, useState } from "react";
import {
  Link,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { ArrowRight, FileText } from "lucide-react";
import type { User } from "../lib/types";
import { api, post } from "../lib/api";
import { useSession } from "../app/session";
import { useQuery } from "@tanstack/react-query";
import { ErrorNotice, Notice } from "../components/ui";
export default function Auth() {
  const { t } = useLanguage();

  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const [mode, setMode] = useState(
    params.has("token") || window.location.hash.includes("token=")
      ? params.get("purpose") === "signup"
        ? "signup-verify"
        : params.get("purpose") === "recover"
          ? "reset"
          : "login"
      : (
          {
            "/register": "register",
            "/forgot-password": "recover",
          } as Record<string, string>
        )[pathname] || "login",
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [token, setToken] = useState(() => {
    const value =
      new URLSearchParams(window.location.hash.slice(1)).get("token") ||
      params.get("token") ||
      "";
    return value;
  });
  useEffect(() => {
    if (token)
      window.history.replaceState(
        null,
        "",
        window.location.pathname +
          "?purpose=" +
          (params.get("purpose") || "recover"),
      );
  }, [token, params]);
  const options = useQuery({
    queryKey: ["auth-options"],
    queryFn: () =>
      api<{ google: boolean; email: boolean; google_login_url: string }>(
        "/auth/options",
      ),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [message, setMessage] = useState("");
  const { refresh } = useSession();
  const navigate = useNavigate();
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    setMessage("");
    setBusy(true);
    try {
      if (mode === "recover") {
        await post("/auth/recover", { email });
        setMessage(
          t(
            "If this account can be recovered, recovery instructions will be sent to its email address.",
          ),
        );
      } else if (mode === "reset") {
        if (password !== confirmPassword)
          throw Error(t("Passwords do not match."));
        await post("/auth/reset", { token, password });
        setMessage(t("Password updated. Sign in with your new password."));
        setMode("login");
        setPassword("");
        setConfirmPassword("");
        setToken("");
      } else if (mode === "signup-verify") {
        const result = await post<{ setup_token: string }>(
          "/auth/registration/verify",
          { token },
        );
        setToken(result.setup_token);
        setMode("create-password");
        setMessage(t("Email verified. Create your password to finish."));
      } else if (mode === "create-password") {
        if (password !== confirmPassword)
          throw Error(t("Passwords do not match."));
        await post("/auth/registration/complete", {
          token,
          password,
          confirm_password: confirmPassword,
        });
        setMode("login");
        setPassword("");
        setConfirmPassword("");
        setToken("");
        setMessage(t("Account created. Sign in to continue."));
      } else if (mode === "register") {
        await post("/auth/registration/start", { email });
        setMessage(
          t(
            "If this address can be registered, check your email for a verification link. No account is activated until verification.",
          ),
        );
      } else {
        await post<User>("/auth/login", { email, password });
        const session = await refresh();
        if (!session)
          throw Error(
            t(
              "Your session could not be restored. Check browser cookie settings or use the configured application URL.",
            ),
          );
        navigate("/dashboard", { replace: true });
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="auth-page page">
      <div className="auth-intro">
        <p className="eyebrow">{t("A PRIVATE PLACE FOR YOUR DOCUMENTS")}</p>
        <h1>
          {t("Keep the source.")}
          <br />
          <em>{t("Keep the context.")}</em>
        </h1>
        <p>
          {t(
            "Return to your analyses, inspect supporting passages and export a record of your findings.",
          )}
        </p>
        <div className="auth-detail">
          <FileText size={26} />
          <p>
            {t(
              "Evidence stays connected to the document version you reviewed.",
            )}
          </p>
        </div>
      </div>
      <div className="panel auth-form">
        <p className="eyebrow">{t("YOUR VERIORA WORKSPACE")}</p>
        <h2>
          {
            (
              {
                login: t("Welcome back"),
                register: t("Create an account"),
                recover: t("Recover your account"),
                reset: t("Create a new password"),
                "signup-verify": t("Confirm your email"),
                "create-password": t("Create your password"),
              } as Record<string, string>
            )[mode]
          }
        </h2>
        <p className="muted">
          {mode === "register"
            ? t("Save your documents and revisit your evidence.")
            : t("Use your account to access your saved documents.")}
        </p>
        {params.get("oauth") === "failed" && (
          <Notice warning>
            {t(
              "Google sign-in could not be completed. Start a fresh sign-in in this browser. Avoid in-app browsers if cookies are blocked.",
            )}
          </Notice>
        )}
        {["login", "register"].includes(mode) && (
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(undefined);
              try {
                // Establish the cookie through a top-level request on the configured callback origin.
                const target =
                  options.data?.google_login_url ||
                  `${window.location.origin}/api/v1/auth/google/login`;
                window.location.assign(target);
              } catch (e) {
                setError(e);
                setBusy(false);
              }
            }}
          >
            {t("Continue with Google")}
          </button>
        )}
        {options.data && !options.data.google && (
          <p className="small-copy muted">
            {t("Google sign-in is not configured on this deployment.")}
          </p>
        )}
        {["register", "signup-verify", "create-password"].includes(mode) && (
          <ol className="signup-steps" aria-label={t("Registration steps")}>
            {[t("Email"), t("Verify"), t("Password")].map((step, index) => (
              <li
                key={step}
                aria-current={
                  index ===
                  (mode === "register" ? 0 : mode === "signup-verify" ? 1 : 2)
                    ? "step"
                    : undefined
                }
              >
                <span>{index + 1}</span>
                {step}
              </li>
            ))}
          </ol>
        )}
        <form onSubmit={submit} className="fields">
          {!["reset", "signup-verify", "create-password"].includes(
            mode,
          ) && (
            <label>
              {t("Email address")}
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
          )}
          {["login", "reset", "create-password"].includes(mode) && (
            <label>
              {mode === "create-password" || mode === "reset"
                ? t("Create Password")
                : t("Password")}
              <input
                type="password"
                aria-label={
                  mode === "create-password" || mode === "reset"
                    ? t("Create Password")
                    : t("Password")
                }
                aria-describedby="password-help"
                required
                minLength={12}
                maxLength={128}
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <small id="password-help" className="muted">
                {t("At least 12 characters.")}
              </small>
            </label>
          )}
          {["reset", "create-password"].includes(mode) && (
            <label>
              {t("Confirm Password")}
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={128}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </label>
          )}
          {mode === "signup-verify" && (
            <p className="muted">
              {t(
                "Confirm ownership using your emailed link. No password or active account has been created yet.",
              )}
            </p>
          )}
          <ErrorNotice error={error || options.error} />
          {message && <Notice>{message}</Notice>}
          <button className="button" disabled={busy}>
            {busy
              ? t("Please wait…")
              : (
                  {
                    login: t("Sign in"),
                    register: t("Send verification link"),
                    "signup-verify": t("Continue"),
                    "create-password": t("Create account"),
                    recover: t("Send recovery instructions"),
                    reset: t("Update password"),
                  } as Record<string, string>
                )[mode]}
            <ArrowRight size={17} />
          </button>
        </form>
        <div className="auth-links">
          {mode === "login" ? (
            <>
              <button className="text-link" onClick={() => setMode("recover")}>
                {t("Forgot your password?")}
              </button>
              <p>
                {t("New to Veriora?")}{" "}
                <button
                  className="text-link"
                  onClick={() => {
                    setMode("register");
                    setError(undefined);
                  }}
                >
                  {t("Create an account")}
                </button>
              </p>
            </>
          ) : (
            <button
              className="text-link"
              onClick={() => {
                setMode("login");
                setError(undefined);
              }}
            >
              {t("Back to sign in")}
            </button>
          )}
        </div>
        <p className="small-copy muted">
          {t("Just exploring?")}{" "}
          <Link to="/analyze">{t("Start with a limited guest session.")}</Link>
        </p>
      </div>
    </section>
  );
}
