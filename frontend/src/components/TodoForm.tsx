import { useState, type FormEvent, type CSSProperties } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type Todo } from "../api";
import { qk } from "../queryClient";

type CreateInput = { title: string; due_at: string | null };

export function TodoForm() {
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const queryClient = useQueryClient();

  const createTodo = useMutation({
    mutationFn: (body: CreateInput) => api.post<Todo>("/todos", body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.todos });
      setTitle("");
      setDueAt("");
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    createTodo.mutate({
      title: title.trim(),
      due_at: dueAt ? new Date(dueAt).toISOString() : null,
    });
  }

  const errorMsg =
    createTodo.error instanceof ApiError
      ? createTodo.error.message
      : createTodo.error
        ? "Failed to create todo."
        : null;

  return (
    <form onSubmit={onSubmit} style={styles.form} noValidate>
      <label style={styles.titleField}>
        <span style={styles.fieldLabel}>Title</span>
        <input
          name="title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Buy milk, call mom…"
          autoComplete="off"
          spellCheck={false}
          required
          style={styles.input}
        />
      </label>
      <label style={styles.dueField}>
        <span style={styles.fieldLabel}>Due (optional)</span>
        <input
          type="datetime-local"
          name="due_at"
          value={dueAt}
          onChange={(e) => setDueAt(e.target.value)}
          autoComplete="off"
          style={styles.input}
        />
      </label>
      <button type="submit" disabled={createTodo.isPending} style={styles.submit}>
        {createTodo.isPending ? "Adding…" : "Add"}
      </button>
      <div aria-live="polite" style={{ width: "100%" }}>
        {errorMsg && <div style={styles.error}>{errorMsg}</div>}
      </div>
    </form>
  );
}

const styles: Record<string, CSSProperties> = {
  form: { display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" },
  titleField: { display: "flex", flexDirection: "column", flex: "1 1 200px", minWidth: 0 },
  dueField: { display: "flex", flexDirection: "column" },
  fieldLabel: { fontSize: 12, color: "#6b7280", marginBottom: 4 },
  input: { padding: 8, fontSize: 15, border: "1px solid #d1d5db", borderRadius: 6 },
  submit: {
    padding: "8px 14px",
    fontSize: 15,
    border: "1px solid #d1d5db",
    background: "white",
    borderRadius: 6,
  },
  error: { color: "#b91c1c", marginTop: 8, fontSize: 14 },
};
