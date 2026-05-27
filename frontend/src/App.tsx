import { useState } from "react";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { useNotifications } from "./hooks/useNotifications";
import { Login } from "./pages/Login";
import { Todos } from "./pages/Todos";
import { Notifications } from "./pages/Notifications";

function Shell() {
  const { user, loading, logout } = useAuth();
  const [tab, setTab] = useState<"todos" | "notif">("todos");
  // Both Shell and Notifications subscribe to the same query key, so this
  // shares the cache and the poll interval — no prop drilling, no double-fetch.
  const { data: notifications } = useNotifications();
  const unread = notifications?.filter((n) => !n.read_at).length ?? 0;

  if (loading) return <p style={{ padding: 24 }}>Loading…</p>;
  if (!user) return <Login />;

  return (
    <div style={{ fontFamily: "system-ui", maxWidth: 760, margin: "0 auto", padding: 24 }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <h1 style={{ margin: 0 }}>Todo</h1>
        <nav style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button onClick={() => setTab("todos")} disabled={tab === "todos"}>
            Todos
          </button>
          <button onClick={() => setTab("notif")} disabled={tab === "notif"}>
            Notifications{unread > 0 ? ` (${unread})` : ""}
          </button>
          <span style={{ color: "#666", marginLeft: 8 }}>{user.email}</span>
          <button onClick={logout}>Sign out</button>
        </nav>
      </header>
      {tab === "todos" ? <Todos /> : <Notifications />}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
