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
    error instanceof ApiError ? error.message : error ? "load failed" : null;

  return (
    <section>
      <h2>Notifications</h2>
      {errorMsg && <p style={{ color: "#c00" }}>{errorMsg}</p>}
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
                <div style={{ fontSize: 12, color: "#666" }}>
                  {new Date(n.created_at).toLocaleString()}
                </div>
              </div>
              {!n.read_at && (
                <button onClick={() => markRead.mutate(n.id)} disabled={markRead.isPending}>
                  Mark read
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
