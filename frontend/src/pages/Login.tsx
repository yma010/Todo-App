import { useState, type FormEvent } from "react";
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
      setError(err instanceof ApiError ? err.message : "request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={styles.wrap}>
      <h1>{mode === "login" ? "Sign in" : "Create account"}</h1>
      <form onSubmit={onSubmit} style={styles.form}>
        <label style={styles.label}>
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            style={styles.input}
          />
        </label>
        <label style={styles.label}>
          Password
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            style={styles.input}
          />
          {mode === "register" && (
            <small style={{ color: "#666" }}>
              Must be at least 12 characters and include at least one number and one symbol.
            </small>
          )}
        </label>
        {error && <div style={styles.error}>{error}</div>}
        <button type="submit" disabled={busy} style={styles.primary}>
          {busy ? "..." : mode === "login" ? "Sign in" : "Register"}
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
        {mode === "login" ? "Need an account? Register" : "Have an account? Sign in"}
      </button>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  wrap: { maxWidth: 360, margin: "10vh auto", fontFamily: "system-ui", padding: 24 },
  form: { display: "flex", flexDirection: "column", gap: 12, marginTop: 12 },
  label: { display: "flex", flexDirection: "column", gap: 4 },
  input: { padding: "8px 10px", fontSize: 16, border: "1px solid #ccc", borderRadius: 4 },
  primary: { padding: "10px", fontSize: 16, background: "#0a5", color: "white", border: 0, borderRadius: 4, cursor: "pointer" },
  link: { marginTop: 12, background: "none", border: 0, color: "#0a5", cursor: "pointer" },
  error: { color: "#c00", background: "#fee", padding: 8, borderRadius: 4 },
};
