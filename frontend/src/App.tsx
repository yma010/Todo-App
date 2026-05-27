import {
  useCallback,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { useNotifications } from "./hooks/useNotifications";
import { Login } from "./pages/Login";
import { Todos } from "./pages/Todos";
import { Notifications } from "./pages/Notifications";

type Tab = "todos" | "notif";
const TAB_ORDER: Tab[] = ["todos", "notif"];

function readTabFromUrl(): Tab {
  if (typeof window === "undefined") return "todos";
  const v = new URLSearchParams(window.location.search).get("tab");
  return v === "notif" ? "notif" : "todos";
}

// useState + URL sync, with the URL write folded into the setter rather
// than an effect that watches state. Tab only changes from user events
// (button click, arrow-key nav), so the setter is the right place to
// update the URL — no need to subscribe to state changes via useEffect.
function useTabState(): [Tab, (next: Tab) => void] {
  const [tab, setTabState] = useState<Tab>(readTabFromUrl);
  const setTab = useCallback((next: Tab) => {
    setTabState(next);
    const params = new URLSearchParams(window.location.search);
    params.set("tab", next);
    window.history.replaceState(null, "", `?${params.toString()}`);
  }, []);
  return [tab, setTab];
}

function Shell() {
  const { user, loading, logout } = useAuth();
  const [tab, setTab] = useTabState();
  const { data: notifications } = useNotifications();
  const unread = notifications?.filter((n) => !n.read_at).length ?? 0;
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({
    todos: null,
    notif: null,
  });

  if (loading) {
    return (
      <p role="status" aria-live="polite" style={{ padding: 24 }}>
        Loading…
      </p>
    );
  }
  if (!user) return <Login />;

  function activateTab(next: Tab) {
    setTab(next);
    // Automatic-activation tab pattern: focus follows selection.
    tabRefs.current[next]?.focus();
  }

  function handleTabsKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const i = TAB_ORDER.indexOf(tab);
    let next: Tab | null = null;
    if (e.key === "ArrowRight") next = TAB_ORDER[(i + 1) % TAB_ORDER.length];
    else if (e.key === "ArrowLeft")
      next = TAB_ORDER[(i - 1 + TAB_ORDER.length) % TAB_ORDER.length];
    else if (e.key === "Home") next = TAB_ORDER[0];
    else if (e.key === "End") next = TAB_ORDER[TAB_ORDER.length - 1];
    if (next && next !== tab) {
      e.preventDefault();
      activateTab(next);
    }
  }

  return (
    <div style={styles.page}>
      <a href="#main" className="skip-link">
        Skip to main content
      </a>
      <header style={styles.header}>
        <h1 style={styles.title}>Todo</h1>
        <nav style={styles.nav} aria-label="Main">
          <div
            role="tablist"
            aria-label="Sections"
            style={styles.tabGroup}
            onKeyDown={handleTabsKeyDown}
          >
            <TabButton
              id="tab-todos"
              controls="panel-todos"
              active={tab === "todos"}
              onClick={() => setTab("todos")}
              btnRef={(el) => {
                tabRefs.current.todos = el;
              }}
            >
              Todos
            </TabButton>
            <TabButton
              id="tab-notif"
              controls="panel-notif"
              active={tab === "notif"}
              onClick={() => setTab("notif")}
              btnRef={(el) => {
                tabRefs.current.notif = el;
              }}
            >
              Notifications
              {unread > 0 ? (
                <>
                  {" "}
                  <span style={styles.badge} aria-label={`${unread} unread`}>
                    {unread}
                  </span>
                </>
              ) : null}
            </TabButton>
          </div>
          <div style={styles.account}>
            <span style={styles.email} title={user.email}>
              {user.email}
            </span>
            <button onClick={logout} style={styles.signOut}>
              Sign Out
            </button>
          </div>
        </nav>
      </header>
      <main id="main">
        {tab === "todos" && (
          <section role="tabpanel" id="panel-todos" aria-labelledby="tab-todos">
            <Todos />
          </section>
        )}
        {tab === "notif" && (
          <section role="tabpanel" id="panel-notif" aria-labelledby="tab-notif">
            <Notifications />
          </section>
        )}
      </main>
    </div>
  );
}

function TabButton({
  id,
  controls,
  active,
  onClick,
  btnRef,
  children,
}: {
  id: string;
  controls: string;
  active: boolean;
  onClick: () => void;
  btnRef: (el: HTMLButtonElement | null) => void;
  children: ReactNode;
}) {
  return (
    <button
      ref={btnRef}
      id={id}
      role="tab"
      aria-selected={active}
      aria-controls={controls}
      tabIndex={active ? 0 : -1}
      onClick={onClick}
      style={{ ...styles.tabButton, ...(active ? styles.tabButtonActive : null) }}
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
    padding: "24px clamp(16px, 4vw, 48px)",
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
  },
  tabButtonActive: {
    background: "white",
    color: "#111827",
    fontWeight: 600,
    boxShadow: "0 1px 2px rgba(0, 0, 0, 0.06)",
  },
  badge: {
    display: "inline-block",
    minWidth: 18,
    padding: "0 6px",
    fontSize: 11,
    fontWeight: 600,
    lineHeight: "18px",
    textAlign: "center",
    color: "white",
    background: "#dc2626",
    borderRadius: 9,
    fontVariantNumeric: "tabular-nums",
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
  },
};
