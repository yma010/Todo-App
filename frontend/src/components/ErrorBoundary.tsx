import { Component, type CSSProperties, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

/**
 * Catches render-time exceptions anywhere below it and shows a recovery
 * UI instead of a blank screen. Required because React only catches
 * errors during rendering / lifecycle / constructor — runtime fetch
 * errors are handled by the query layer; THIS handles "I read a field
 * that was undefined and crashed Todos.tsx" class of bugs.
 *
 * Must be a class component — React's `getDerivedStateFromError` /
 * `componentDidCatch` hooks have no functional equivalent.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // In prod this would go to Sentry / Honeybadger / etc. For now,
    // console — at least it's visible in the dev tools.
    console.error("ErrorBoundary caught a render error:", error, info);
  }

  private reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <main role="alert" style={styles.wrap}>
          <h1 style={styles.heading}>Something went wrong</h1>
          <p style={styles.message}>
            {this.state.error.message || "An unexpected error occurred."}
          </p>
          <div style={styles.actions}>
            <button onClick={this.reset} style={styles.btn}>
              Try Again
            </button>
            <button onClick={() => window.location.reload()} style={styles.btnPrimary}>
              Reload Page
            </button>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}

const styles: Record<string, CSSProperties> = {
  wrap: { maxWidth: 480, margin: "10vh auto", padding: 24, textAlign: "center" },
  heading: { margin: 0, fontSize: 28, fontWeight: 600, letterSpacing: "-0.01em" },
  message: { color: "#6b7280", margin: "12px 0 24px" },
  actions: { display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" },
  btn: {
    padding: "8px 16px",
    fontSize: 14,
    border: "1px solid #d1d5db",
    background: "white",
    borderRadius: 6,
  },
  btnPrimary: {
    padding: "8px 16px",
    fontSize: 14,
    border: 0,
    background: "#059669",
    color: "white",
    borderRadius: 6,
    fontWeight: 600,
  },
};
