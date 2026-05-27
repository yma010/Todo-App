import { useState, type CSSProperties } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type Todo } from "../api";
import { qk } from "../queryClient";

type UpdateBody = {
  title?: string;
  due_at?: string;
  clear_due_at?: boolean;
};

export function TodoItem({ todo }: { todo: Todo }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(todo.title);
  const [dueAt, setDueAt] = useState(toLocalInput(todo.due_at));
  const queryClient = useQueryClient();

  // Optimistic toggle: write the cache immediately, roll back on error,
  // re-fetch on settle so the server's truth wins regardless.
  const toggleComplete = useMutation({
    mutationFn: (completed: boolean) =>
      api.patch<Todo>(`/todos/${todo.id}`, { completed }),
    onMutate: async (completed) => {
      await queryClient.cancelQueries({ queryKey: qk.todos });
      const previous = queryClient.getQueryData<Todo[]>(qk.todos);
      queryClient.setQueryData<Todo[]>(qk.todos, (old) =>
        (old ?? []).map((t) => (t.id === todo.id ? { ...t, completed } : t)),
      );
      return { previous };
    },
    onError: (_err, _completed, context) => {
      if (context?.previous) {
        queryClient.setQueryData(qk.todos, context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: qk.todos });
    },
  });

  const saveEdit = useMutation({
    mutationFn: (body: UpdateBody) => api.patch<Todo>(`/todos/${todo.id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.todos });
      setEditing(false);
    },
  });

  const remove = useMutation({
    mutationFn: () => api.del<void>(`/todos/${todo.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.todos });
    },
  });

  function handleSaveEdit() {
    const body: UpdateBody = { title: title.trim() };
    if (dueAt) body.due_at = new Date(dueAt).toISOString();
    else body.clear_due_at = true;
    saveEdit.mutate(body);
  }

  function handleRemove() {
    // Curly quotes around the title — interview-grade typography.
    if (!confirm(`Delete “${todo.title}”?`)) return;
    remove.mutate();
  }

  const busy = toggleComplete.isPending || saveEdit.isPending || remove.isPending;
  const error = toggleComplete.error ?? saveEdit.error ?? remove.error ?? null;
  const errorMsg =
    error instanceof ApiError ? error.message : error ? "Update failed." : null;

  const toggleLabel = todo.completed
    ? `Mark "${todo.title}" as incomplete`
    : `Mark "${todo.title}" as complete`;

  return (
    <li style={{ ...styles.row, opacity: todo.completed ? 0.55 : 1 }}>
      <input
        type="checkbox"
        checked={todo.completed}
        onChange={(e) => toggleComplete.mutate(e.target.checked)}
        aria-label={toggleLabel}
      />
      {editing ? (
        <div style={styles.editArea}>
          <input
            name="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            aria-label="Title"
            style={{ ...styles.input, flex: "1 1 200px" }}
          />
          <input
            type="datetime-local"
            name="due_at"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
            aria-label="Due date"
            style={styles.input}
          />
          <button onClick={handleSaveEdit} disabled={saveEdit.isPending} style={styles.btn}>
            {saveEdit.isPending ? "Saving…" : "Save"}
          </button>
          <button
            onClick={() => setEditing(false)}
            disabled={saveEdit.isPending}
            style={styles.btn}
          >
            Cancel
          </button>
        </div>
      ) : (
        <div style={styles.viewArea}>
          <div
            style={{
              textDecoration: todo.completed ? "line-through" : "none",
              overflowWrap: "anywhere",
            }}
          >
            {todo.title}
          </div>
          {todo.due_at && (
            <div style={{ fontSize: 12, color: "#6b7280" }}>
              due {formatDue(todo.due_at)}
            </div>
          )}
        </div>
      )}
      {!editing && (
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={() => setEditing(true)} disabled={busy} style={styles.btn}>
            Edit
          </button>
          <button onClick={handleRemove} disabled={busy} style={styles.btn}>
            Delete
          </button>
        </div>
      )}
      <div aria-live="polite" style={{ width: "100%" }}>
        {errorMsg && <div style={styles.error}>{errorMsg}</div>}
      </div>
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

const styles: Record<string, CSSProperties> = {
  row: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 12px",
    borderBottom: "1px solid #e5e7eb",
    flexWrap: "wrap",
    minWidth: 0,
  },
  viewArea: { flex: 1, display: "flex", flexDirection: "column", gap: 2, minWidth: 0 },
  editArea: { flex: 1, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" },
  input: { padding: 6, fontSize: 14, border: "1px solid #d1d5db", borderRadius: 4 },
  btn: {
    padding: "5px 10px",
    fontSize: 13,
    border: "1px solid #d1d5db",
    background: "white",
    borderRadius: 6,
  },
  error: { color: "#b91c1c", marginTop: 8, fontSize: 13 },
};
