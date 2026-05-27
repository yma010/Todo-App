import { useEffect, useState } from "react";
import { api, ApiError, type Notification } from "../api";

export function Notifications({ onCountChange }: { onCountChange: (n: number) => void }) {
  const [items, setItems] = useState<Notification[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const rows = await api.get<Notification[]>("/notifications");
        if (!alive) return;
        setItems(rows);
        onCountChange(rows.filter((r) => !r.read_at).length);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof ApiError ? e.message : "load failed");
      }
    }
    load();
    const id = setInterval(load, 30_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [onCountChange]);

  async function markRead(id: string) {
    try {
      const updated = await api.post<Notification>(`/notifications/${id}/mark-read`);
      setItems((prev) => {
        const next = prev.map((x) => (x.id === id ? updated : x));
        onCountChange(next.filter((r) => !r.read_at).length);
        return next;
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "update failed");
    }
  }

  return (
    <section>
      <h2>Notifications</h2>
      {error && <p style={{ color: "#c00" }}>{error}</p>}
      {items.length === 0 ? (
        <p style={{ color: "#666" }}>None yet.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, border: "1px solid #eee", borderRadius: 6 }}>
          {items.map((n) => (
            <li
              key={n.id}
              style={{
                padding: "10px 12px",
                borderBottom: "1px solid #eee",
                background: n.read_at ? "white" : "#fffbe6",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div>
                <div>{n.message}</div>
                <div style={{ fontSize: 12, color: "#666" }}>{new Date(n.created_at).toLocaleString()}</div>
              </div>
              {!n.read_at && <button onClick={() => markRead(n.id)}>Mark read</button>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
