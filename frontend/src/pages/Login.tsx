import { useState, type FormEvent, type CSSProperties } from "react";
import { ApiError } from "../api";
import { useAuth } from "../auth/AuthContext";

export function Login() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const heading = mode === "login" ? "Sign In" : "Create Account";
  const submitIdle = mode === "login" ? "Sign In" : "Create Account";
  const submitBusy = mode === "login" ? "Signing In…" : "Creating Account…";

  return (
    <main style={styles.wrap}>
      <h1 style={styles.heading}>{heading}</h1>
      <form onSubmit={onSubmit} style={styles.form} noValidate>
        <label style={styles.label}>
          Email
          <input
            type="email"
            name="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            spellCheck={false}
            inputMode="email"
            style={styles.input}
          />
        </label>
        <label style={styles.label}>
          Password
          <input
            type="password"
            name="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            spellCheck={false}
            style={styles.input}
          />
          {mode === "register" && (
            <small style={styles.hint}>
              Must be at least 12 characters and include at least one number and one symbol.
            </small>
          )}
        </label>
        {/* Live region is always mounted so the screen reader announces
            the error when it appears (and the clear when it goes). */}
        <div aria-live="polite">
          {error && <div style={styles.error}>{error}</div>}
        </div>
        <button type="submit" disabled={busy} style={styles.primary}>
          {busy ? submitBusy : submitIdle}
        </button>
      </form>
      <button
        type="button"
        onClick={() => {
          setMode(mode === "login" ? "register" : "login");
          setError(null);
        }}
        style={styles.link}
      >
        {mode === "login" ? "Need an account? Register" : "Have an account? Sign In"}
      </button>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: { maxWidth: 360, margin: "10vh auto", padding: 24 },
  heading: { margin: 0, fontSize: 28, fontWeight: 600, letterSpacing: "-0.01em" },
  form: { display: "flex", flexDirection: "column", gap: 12, marginTop: 16 },
  label: { display: "flex", flexDirection: "column", gap: 4, fontSize: 14, color: "#374151" },
  input: { padding: "8px 10px", fontSize: 16, border: "1px solid #d1d5db", borderRadius: 6 },
  hint: { color: "#6b7280", fontSize: 12 },
  primary: {
    padding: "10px",
    fontSize: 16,
    fontWeight: 600,
    background: "#059669",
    color: "white",
    border: 0,
    borderRadius: 6,
  },
  link: {
    marginTop: 12,
    background: "none",
    border: 0,
    color: "#059669",
    padding: 4,
  },
  error: {
    color: "#b91c1c",
    background: "#fee2e2",
    padding: "10px 12px",
    borderRadius: 6,
    fontSize: 14,
  },
};
