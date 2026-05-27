import { useState, type FormEvent } from "react";
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
        ? "create failed"
        : null;

  return (
    <form
      onSubmit={onSubmit}
      style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}
    >
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
      <button type="submit" disabled={createTodo.isPending} style={{ padding: "8px 14px", fontSize: 15 }}>
        {createTodo.isPending ? "..." : "Add"}
      </button>
      {errorMsg && <div style={{ color: "#c00", width: "100%" }}>{errorMsg}</div>}
    </form>
  );
}
