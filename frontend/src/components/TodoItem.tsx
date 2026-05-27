import { useState } from "react";
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
  // re-fetch on settle so the server's truth wins regardless. This is the
  // canonical React Query pattern for "instant feedback on a network
  // round-trip" — onMutate fires synchronously before the request leaves.
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
    if (!confirm(`Delete "${todo.title}"?`)) return;
    remove.mutate();
  }

  const busy = toggleComplete.isPending || saveEdit.isPending || remove.isPending;
  const error =
    toggleComplete.error ?? saveEdit.error ?? remove.error ?? null;
  const errorMsg = error instanceof ApiError ? error.message : error ? "update failed" : null;

  return (
    <li style={{ ...styles.row, opacity: todo.completed ? 0.55 : 1 }}>
      <input
        type="checkbox"
        checked={todo.completed}
        onChange={(e) => toggleComplete.mutate(e.target.checked)}
        aria-label="complete"
      />
      {editing ? (
        <div style={styles.editArea}>
          <input value={title} onChange={(e) => setTitle(e.target.value)} style={styles.input} />
          <input
            type="datetime-local"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
            style={styles.input}
          />
          <button onClick={handleSaveEdit} disabled={saveEdit.isPending}>Save</button>
          <button onClick={() => setEditing(false)} disabled={saveEdit.isPending}>Cancel</button>
        </div>
      ) : (
        <div style={styles.viewArea}>
          <div style={{ textDecoration: todo.completed ? "line-through" : "none" }}>
            {todo.title}
          </div>
          {todo.due_at && (
            <div style={{ fontSize: 12, color: "#666" }}>due {formatDue(todo.due_at)}</div>
          )}
        </div>
      )}
      {!editing && (
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={() => setEditing(true)} disabled={busy}>Edit</button>
          <button onClick={handleRemove} disabled={busy}>Delete</button>
        </div>
      )}
      {errorMsg && <div style={{ color: "#c00", width: "100%" }}>{errorMsg}</div>}
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
