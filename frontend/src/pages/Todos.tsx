import { useEffect, useState } from "react";
import { api, ApiError, type Todo } from "../api";
import { TodoForm } from "../components/TodoForm";
import { TodoItem } from "../components/TodoItem";

export function Todos() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Todo[]>("/todos")
      .then(setTodos)
      .catch((e) => setError(e instanceof ApiError ? e.message : "load failed"))
      .finally(() => setLoading(false));
  }, []);

  function onCreated(t: Todo) {
    setTodos((prev) => [t, ...prev]);
  }

  function onChanged(t: Todo) {
    setTodos((prev) => prev.map((x) => (x.id === t.id ? t : x)));
  }

  function onDeleted(id: string) {
    setTodos((prev) => prev.filter((x) => x.id !== id));
  }

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "#c00" }}>{error}</p>;

  return (
    <section>
      <h2>Your todos</h2>
      <TodoForm onCreated={onCreated} />
      {todos.length === 0 ? (
        <p style={{ color: "#666", marginTop: 12 }}>Nothing yet. Add one above.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, marginTop: 16, border: "1px solid #eee", borderRadius: 6 }}>
          {todos.map((t) => (
            <TodoItem key={t.id} todo={t} onChanged={onChanged} onDeleted={onDeleted} />
          ))}
        </ul>
      )}
    </section>
  );
}
