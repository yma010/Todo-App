import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "./api";

// Query keys live in one place so a typo on either side of the
// query/invalidate pair becomes a TS error rather than a silent miss.
export const qk = {
  me: ["me"] as const,
  todos: ["todos"] as const,
  notifications: ["notifications"] as const,
};

// Global 401 handler: when any authenticated request returns 401,
// treat the session as gone. Clears the cached user (forcing
// AuthContext to flip to "logged out" → Shell renders <Login />) and
// drops per-user data so a future login starts fresh.
//
// Defined before queryClient because the caches reference it via
// closure; the lookup of `queryClient` is deferred to call-time, when
// the QueryClient is already initialized.
function handle401(error: unknown): void {
  if (!(error instanceof ApiError) || error.status !== 401) return;
  queryClient.setQueryData(qk.me, null);
  queryClient.removeQueries({ queryKey: qk.todos });
  queryClient.removeQueries({ queryKey: qk.notifications });
}

const queryCache = new QueryCache({
  onError: handle401,
});

const mutationCache = new MutationCache({
  onError: handle401,
});

// Don't retry 4xx — 401 means "not logged in", 422/409 means "user
// input is bad," neither will be fixed by trying again. Network errors
// and 5xx get one retry.
export const queryClient = new QueryClient({
  queryCache,
  mutationCache,
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          return false;
        }
        return failureCount < 1;
      },
      // 30s of "fresh" means component remounts don't trigger a refetch
      // immediately; window-focus refetch is still allowed.
      staleTime: 30_000,
      refetchOnWindowFocus: true,
    },
    mutations: {
      // Surface mutation errors to onError handlers in components; don't
      // retry write operations by default.
      retry: false,
    },
  },
});
