import { useState, type CSSProperties } from "react";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { useNotifications } from "./hooks/useNotifications";
import { Login } from "./pages/Login";
import { Todos } from "./pages/Todos";
import { Notifications } from "./pages/Notifications";

type Tab = "todos" | "notif";

function Shell() {
  const { user, loading, logout } = useAuth();
  const [tab, setTab] = useState<Tab>("todos");
  // Both Shell and Notifications subscribe to the same query key, so this
  // shares the cache and the poll interval — no prop drilling, no double-fetch.
  const { data: notifications } = useNotifications();
  const unread = notifications?.filter((n) => !n.read_at).length ?? 0;

  if (loading) return <p style={{ padding: 24 }}>Loading…</p>;
  if (!user) return <Login />;

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <h1 style={styles.title}>Todo</h1>
        <nav style={styles.nav} aria-label="Main">
          <div role="tablist" style={styles.tabGroup}>
            <TabButton active={tab === "todos"} onClick={() => setTab("todos")}>
              Todos
            </TabButton>
            <TabButton active={tab === "notif"} onClick={() => setTab("notif")}>
              Notifications{unread > 0 ? ` (${unread})` : ""}
            </TabButton>
          </div>
          <div style={styles.account}>
            <span style={styles.email} title={user.email}>{user.email}</span>
            <button onClick={logout} style={styles.signOut}>Sign out</button>
          </div>
        </nav>
      </header>
      {tab === "todos" ? <Todos /> : <Notifications />}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      style={{
        ...styles.tabButton,
        ...(active ? styles.tabButtonActive : null),
      }}
    >
      {children}
    </button>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    fontFamily: "system-ui, -apple-system, sans-serif",
    maxWidth: 760,
    margin: "0 auto",
    padding: 24,
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: 16,
    marginBottom: 24,
    paddingBottom: 16,
    borderBottom: "1px solid #e5e7eb",
  },
  title: {
    margin: 0,
    fontSize: 24,
    fontWeight: 600,
    letterSpacing: "-0.01em",
  },
  nav: {
    display: "flex",
    alignItems: "center",
    gap: 20,
    flexWrap: "wrap",
  },
  tabGroup: {
    display: "flex",
    gap: 2,
    padding: 3,
    background: "#f3f4f6",
    borderRadius: 8,
  },
  tabButton: {
    padding: "6px 14px",
    fontSize: 14,
    fontWeight: 500,
    border: "none",
    background: "transparent",
    color: "#4b5563",
    borderRadius: 6,
    cursor: "pointer",
  },
  tabButtonActive: {
    background: "white",
    color: "#111827",
    fontWeight: 600,
    boxShadow: "0 1px 2px rgba(0, 0, 0, 0.06)",
  },
  account: {
    display: "flex",
    alignItems: "center",
    gap: 12,
  },
  email: {
    color: "#6b7280",
    fontSize: 13,
    maxWidth: 200,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  signOut: {
    padding: "6px 12px",
    fontSize: 14,
    border: "1px solid #d1d5db",
    background: "white",
    color: "#374151",
    borderRadius: 6,
    cursor: "pointer",
  },
};
