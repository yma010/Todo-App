import { useQuery } from "@tanstack/react-query";
import { api, type Notification } from "../api";
import { qk } from "../queryClient";
import { useAuth } from "../auth/AuthContext";

// One source of truth for the notifications query. Both the header's
// unread badge and the Notifications page subscribe to it; React Query
// dedupes by queryKey so a single network round-trip drives both.
//
// `refetchInterval: 30s` matches the PRD's polling target. `enabled` is
// gated on auth so we don't fire requests on the login screen and waste
// a 401 round-trip.
export function useNotifications() {
  const { user } = useAuth();
  return useQuery({
    queryKey: qk.notifications,
    queryFn: () => api.get<Notification[]>("/notifications"),
    refetchInterval: 30_000,
    enabled: !!user,
  });
}
