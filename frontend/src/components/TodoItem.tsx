import { useState } from "react";
import { api, ApiError, type Todo } from "../api";

type Props = {
  todo: Todo;
  onChanged: (t: Todo) => void;
  onDeleted: (id: string) => void;
};

export function TodoItem({ todo, onChanged, onDeleted }: Props) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(todo.title);
  const [dueAt, setDueAt] = useState(toLocalInput(todo.due_at));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function toggleComplete() {
    // optimistic flip
    const next = { ...todo, completed: !todo.completed };
    onChanged(next);
    try {
      const updated = await api.patch<Todo>(`/todos/${todo.id}`, { completed: next.completed });
      onChanged(updated);
    } catch (err) {
      // roll back
      onChanged(todo);
      setError(err instanceof ApiError ? err.message : "update failed");
    }
  }

  async function saveEdit() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { title: title.trim() };
      if (dueAt) body.due_at = new Date(dueAt).toISOString();
      else body.clear_due_at = true;
      const updated = await api.patch<Todo>(`/todos/${todo.id}`, body);
      onChanged(updated);
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "save failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm(`Delete "${todo.title}"?`)) return;
    setBusy(true);
    try {
      await api.del(`/todos/${todo.id}`);
      onDeleted(todo.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "delete failed");
      setBusy(false);
    }
  }

  return (
    <li style={{ ...styles.row, opacity: todo.completed ? 0.55 : 1 }}>
      <input type="checkbox" checked={todo.completed} onChange={toggleComplete} aria-label="complete" />
      {editing ? (
        <div style={styles.editArea}>
          <input value={title} onChange={(e) => setTitle(e.target.value)} style={styles.input} />
          <input
            type="datetime-local"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
            style={styles.input}
          />
          <button onClick={saveEdit} disabled={busy}>Save</button>
          <button onClick={() => setEditing(false)} disabled={busy}>Cancel</button>
        </div>
      ) : (
        <div style={styles.viewArea}>
          <div style={{ textDecoration: todo.completed ? "line-through" : "none" }}>{todo.title}</div>
          {todo.due_at && (
            <div style={{ fontSize: 12, color: "#666" }}>due {formatDue(todo.due_at)}</div>
          )}
        </div>
      )}
      {!editing && (
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={() => setEditing(true)} disabled={busy}>Edit</button>
          <button onClick={remove} disabled={busy}>Delete</button>
        </div>
      )}
      {error && <div style={{ color: "#c00", width: "100%" }}>{error}</div>}
    </li>
  );
}

function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatDue(iso: string): string {
  return new Date(iso).toLocaleString();
}

const styles: Record<string, React.CSSProperties> = {
  row: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 12px",
    borderBottom: "1px solid #eee",
    flexWrap: "wrap",
  },
  viewArea: { flex: 1, display: "flex", flexDirection: "column", gap: 2 },
  editArea: { flex: 1, display: "flex", gap: 6, flexWrap: "wrap" },
  input: { padding: 6, fontSize: 14 },
};
