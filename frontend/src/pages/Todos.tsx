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

  if (isPending) {
    return (
      <p role="status" aria-live="polite">
        Loading…
      </p>
    );
  }

  const errorMsg =
    error instanceof ApiError ? error.message : error ? "Failed to load todos." : null;

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Your Todos</h2>
      <TodoForm />
      <div aria-live="polite">
        {errorMsg && <p style={{ color: "#b91c1c", marginTop: 12 }}>{errorMsg}</p>}
      </div>
      {!errorMsg && todos.length === 0 ? (
        <p style={{ color: "#6b7280", marginTop: 12 }}>Nothing yet. Add one above.</p>
      ) : (
        todos.length > 0 && (
          <ul
            className="long-list"
            style={{
              listStyle: "none",
              padding: 0,
              marginTop: 16,
              border: "1px solid #e5e7eb",
              borderRadius: 6,
            }}
          >
            {todos.map((t) => (
              <TodoItem key={t.id} todo={t} />
            ))}
          </ul>
        )
      )}
    </section>
  );
}
