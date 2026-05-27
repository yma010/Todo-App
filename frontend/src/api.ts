export class ApiError extends Error {
  status: number;
  payload: unknown;
  constructor(status: number, message: string, payload: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: "include",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const payload = text ? safeJson(text) : null;
  if (!res.ok) {
    const msg = extractMessage(payload) ?? `HTTP ${res.status}`;
    throw new ApiError(res.status, msg, payload);
  }
  return payload as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function extractMessage(payload: unknown): string | null {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (first?.msg) return first.msg;
    }
    if (detail && typeof detail === "object" && "msg" in detail) {
      const msg = (detail as { msg: unknown }).msg;
      if (typeof msg === "string") return msg;
    }
  }
  return null;
}

export const api = {
  get: <T,>(p: string) => request<T>("GET", p),
  post: <T,>(p: string, b?: unknown) => request<T>("POST", p, b),
  patch: <T,>(p: string, b?: unknown) => request<T>("PATCH", p, b),
  del: <T,>(p: string) => request<T>("DELETE", p),
};

export type User = { id: string; email: string; created_at: string };

export type Todo = {
  id: string;
  title: string;
  description: string | null;
  completed: boolean;
  due_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Notification = {
  id: string;
  todo_id: string;
  due_at_snapshot: string;
  message: string;
  created_at: string;
  read_at: string | null;
};
