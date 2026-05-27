import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "./api";

// Don't retry 4xx — 401 means "not logged in", 422/409 means "user input
// is bad," neither will be fixed by trying again. Network errors and 5xx
// get one retry.
export const queryClient = new QueryClient({
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

// Query keys live in one place so a typo on either side of the
// query/invalidate pair becomes a TS error rather than a silent miss.
export const qk = {
  me: ["me"] as const,
  todos: ["todos"] as const,
  notifications: ["notifications"] as const,
};
