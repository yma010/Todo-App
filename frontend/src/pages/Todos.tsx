import { useQuery } from "@tanstack/react-query";
import { api, ApiError, type Todo } from "../api";
import { qk } from "../queryClient";
import { TodoForm } from "../components/TodoForm";
import { TodoItem } from "../components/TodoItem";

export function Todos() {
  const { data: todos = [], isPending, error } = useQuery({
    queryKey: qk.todos,
    queryFn: () => api.get<Todo[]>("/todos"),
  });

  if (isPending) return <p>Loading…</p>;
  if (error) {
    return (
      <p style={{ color: "#c00" }}>
        {error instanceof ApiError ? error.message : "load failed"}
      </p>
    );
  }

  return (
    <section>
      <h2>Your todos</h2>
      <TodoForm />
      {todos.length === 0 ? (
        <p style={{ color: "#666", marginTop: 12 }}>Nothing yet. Add one above.</p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            marginTop: 16,
            border: "1px solid #eee",
            borderRadius: 6,
          }}
        >
          {todos.map((t) => (
            <TodoItem key={t.id} todo={t} />
          ))}
        </ul>
      )}
    </section>
  );
}
