import { useState, type FormEvent } from "react";
import { api, ApiError, type Todo } from "../api";

export function TodoForm({ onCreated }: { onCreated: (t: Todo) => void }) {
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.post<Todo>("/todos", {
        title: title.trim(),
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
      });
      onCreated(created);
      setTitle("");
      setDueAt("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "create failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
      <label style={{ display: "flex", flexDirection: "column", flex: "1 1 200px" }}>
        <span style={{ fontSize: 12, color: "#666" }}>Title</span>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="What needs doing?"
          required
          style={{ padding: 8, fontSize: 15 }}
        />
      </label>
      <label style={{ display: "flex", flexDirection: "column" }}>
        <span style={{ fontSize: 12, color: "#666" }}>Due (optional)</span>
        <input
          type="datetime-local"
          value={dueAt}
          onChange={(e) => setDueAt(e.target.value)}
          style={{ padding: 8, fontSize: 15 }}
        />
      </label>
      <button type="submit" disabled={busy} style={{ padding: "8px 14px", fontSize: 15 }}>
        {busy ? "..." : "Add"}
      </button>
      {error && <div style={{ color: "#c00", width: "100%" }}>{error}</div>}
    </form>
  );
}
