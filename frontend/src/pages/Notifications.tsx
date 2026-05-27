import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type Notification } from "../api";
import { qk } from "../queryClient";
import { useNotifications } from "../hooks/useNotifications";

export function Notifications() {
  const queryClient = useQueryClient();
  const { data: items = [], error } = useNotifications();

  const markRead = useMutation({
    mutationFn: (id: string) =>
      api.post<Notification>(`/notifications/${id}/mark-read`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.notifications });
    },
  });

  const errorMsg =
    error instanceof ApiError ? error.message : error ? "Failed to load notifications." : null;

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Notifications</h2>
      <div aria-live="polite">
        {errorMsg && <p style={{ color: "#b91c1c" }}>{errorMsg}</p>}
      </div>
      {items.length === 0 ? (
        <p style={{ color: "#6b7280" }}>None yet.</p>
      ) : (
        <ul
          className="long-list"
          style={{
            listStyle: "none",
            padding: 0,
            border: "1px solid #e5e7eb",
            borderRadius: 6,
          }}
        >
          {items.map((n) => (
            <li
              key={n.id}
              style={{
                padding: "10px 12px",
                borderBottom: "1px solid #e5e7eb",
                background: n.read_at ? "white" : "#fffbeb",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  {!n.read_at && (
                    // Visible text badge — unread state is conveyed by
                    // both color AND label, so it survives non-color
                    // users (dichromacy, monochrome printout, etc).
                    <span
                      style={{
                        display: "inline-block",
                        padding: "1px 6px",
                        fontSize: 11,
                        fontWeight: 600,
                        color: "#92400e",
                        background: "#fde68a",
                        borderRadius: 4,
                        letterSpacing: "0.04em",
                      }}
                    >
                      Unread
                    </span>
                  )}
                  <span style={{ overflowWrap: "anywhere" }}>{n.message}</span>
                </div>
                <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
                  {new Date(n.created_at).toLocaleString()}
                </div>
              </div>
              {!n.read_at && (
                <button
                  onClick={() => markRead.mutate(n.id)}
                  disabled={markRead.isPending}
                  style={{
                    padding: "6px 10px",
                    fontSize: 13,
                    border: "1px solid #d1d5db",
                    background: "white",
                    borderRadius: 6,
                  }}
                >
                  {markRead.isPending ? "Marking…" : "Mark Read"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
