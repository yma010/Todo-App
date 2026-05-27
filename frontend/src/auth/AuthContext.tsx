import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type User } from "../api";
import { qk } from "../queryClient";

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  // `me` is the source of truth for who's logged in. A 401 here means
  // "not logged in" — handled cleanly by treating no-data as no-user.
  const meQuery = useQuery({
    queryKey: qk.me,
    queryFn: () => api.get<User>("/auth/me"),
    // Auth state can't go stale silently — we want focus refetch.
    staleTime: 0,
  });

  const user: User | null =
    meQuery.data ??
    (meQuery.error instanceof ApiError && meQuery.error.status === 401 ? null : null);

  // `loading` is true only during the very first /me call so the UI can
  // show a spinner instead of flashing the login screen for a logged-in user.
  const loading = meQuery.isPending;

  const loginMutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      api.post<User>("/auth/login", { email, password }),
    onSuccess: (u) => {
      queryClient.setQueryData(qk.me, u);
    },
  });

  const registerMutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      api.post<User>("/auth/register", { email, password }),
    onSuccess: (u) => {
      queryClient.setQueryData(qk.me, u);
    },
  });

  const logoutMutation = useMutation({
    mutationFn: () => api.post<void>("/auth/logout"),
    onSuccess: () => {
      // Drop every cached query that belongs to the previous user.
      // setQueryData(me, null) would also work but `removeQueries`
      // forces a fresh /me on next mount, which matches the intent.
      queryClient.removeQueries({ queryKey: qk.me });
      queryClient.removeQueries({ queryKey: qk.todos });
      queryClient.removeQueries({ queryKey: qk.notifications });
    },
  });

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login: async (email, password) => {
        await loginMutation.mutateAsync({ email, password });
      },
      register: async (email, password) => {
        await registerMutation.mutateAsync({ email, password });
      },
      logout: async () => {
        await logoutMutation.mutateAsync();
      },
    }),
    [user, loading, loginMutation, registerMutation, logoutMutation],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
