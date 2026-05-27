# Product Requirements — Todo App with Due-Date Reminders

**Owner:** Marvin
**Context:** Lennar full-stack interview exercise (Python + React + Postgres)
**Status:** Draft v1
**Last updated:** 2026-05-26

---

## 1. Problem & Goal

A user needs a personal todo list where items can have optional due dates, and the system reminds them as a due date approaches. The exercise tests full-stack fundamentals (auth, CRUD, persistence, isolation per user), an async pattern (background reminder jobs), and production sensibility (validation, error handling, security, tests).

**Goal of the build:** a complete, runnable, defensible application that prioritizes correctness and clarity over feature breadth. A simple solution that works end-to-end and that the candidate can explain line-by-line beats an ambitious half-finished one.

**Non-goals:** real email/SMS delivery, multi-user sharing or collaboration, mobile apps, recurring todos, rich text, attachments, search beyond the obvious, design polish.

## 2. Users & Personas

A single persona: a signed-in individual managing their own todos. There are no admin, team, or org roles. Every authenticated request is scoped to the requesting user; the user can only see and mutate rows they own.

## 3. Scope

### In scope (must have)

The following are required by the brief and form the bar for "done":

- Account registration with email + password
- Login that returns a credential the frontend uses on subsequent requests
- Logout (client-side credential disposal plus server-side invalidation where applicable)
- Create, read, update, delete todos
- Mark a todo complete / incomplete (toggle)
- Optional `due_at` timestamp per todo
- Per-user data isolation (a user cannot read or mutate another user's todos, even by guessing IDs)
- Background reminder job scheduled when a todo with a future `due_at` is created or updated; reminder fires by writing to a `notifications` table (no external send)
- Reminder cancellation when a todo is deleted, completed, or its due date is removed or moved
- Functional UI: list view, create form, edit affordance, delete, complete toggle, in-app notifications view
- Input validation on both client and server
- Error handling with helpful messages (no raw 500s leaking stack traces)
- Tests for at least one critical path (target: auth + reminder scheduling)
- README explaining how to run locally and how AI was used

### Out of scope (won't have, this round)

Password reset, email verification, OAuth/social login, 2FA, tags/labels/projects, sorting beyond due-date and created-at, recurring todos, sub-tasks, file attachments, sharing, real notification delivery (email/SMS/push), websockets/SSE live updates, dark mode polish, full responsive design, internationalization, audit logging, soft deletes, undo.

### Could have (stretch, if time remains under 4 hours)

In-app toast when a notification arrives (polled), a small notification bell with unread count, a "snooze" action that reschedules the reminder, server-sent events instead of polling. Each is documented as "would do next" if not built.

## 4. Functional Requirements

### 4.1 Authentication

A new user registers with an email and password. Email must be a syntactically valid address and unique. Password must be at least 12 characters; the server rejects anything shorter. Passwords are stored only as bcrypt hashes (cost ≥ 12) — never plaintext, never reversible encryption.

Login accepts email + password, verifies the password against the stored hash, and creates a **server-side session**: a row in the `sessions` table with a UUID `id`, the `user_id`, an `expires_at` (default 14 days), and `created_at` / `last_used_at` timestamps. The server returns the session via an HTTP response cookie configured with `HttpOnly` (JavaScript cannot read it, blocking XSS exfiltration), `Secure` (HTTPS only in production; the dev-mode default is `false` and documented), `SameSite=Lax` (the browser refuses to attach the cookie to most cross-site requests, mitigating CSRF), `Path=/`, and a matching `Max-Age`. The cookie value is the opaque session UUID — it contains no user data and no claims.

All `/todos` and `/notifications` routes require a valid session. The `get_current_user` dependency reads the session cookie, looks up the row, rejects the request if the session is missing, expired, or has `revoked_at` set, and updates `last_used_at` on the way through. The user ID is taken from the session row, never from the request body.

Logout deletes (or sets `revoked_at` on) the session row server-side and clears the cookie on the client. Because session validity is checked on every request, logout is immediate and complete — the credential cannot be replayed after logout. This is the property JWT loses without an additional denylist.

### 4.2 Todos

A todo has: `id`, `user_id` (owner), `title` (required, 1–200 chars), `description` (optional, up to 2000 chars), `completed` (bool, default false), `due_at` (optional timestamp, must be ≥ now at create time; updates may move it earlier or later including into the past — that just means no future reminder), `created_at`, `updated_at`.

API endpoints (all under `/api`, all require auth except register/login):

`POST /auth/register`, `POST /auth/login`, `GET /todos`, `POST /todos`, `GET /todos/{id}`, `PATCH /todos/{id}`, `DELETE /todos/{id}`, `GET /notifications`, `POST /notifications/{id}/mark-read`.

Every read and write filters by `user_id = <current_user>`. A 404 (not 403) is returned for IDs the user does not own — this avoids leaking the existence of other users' rows.

### 4.3 Reminders

When a todo is created or updated with a `due_at` in the future, the server schedules a job to fire at `due_at - REMINDER_LEAD` (default lead time: 15 minutes; configurable via env). When the job fires it inserts a row into `notifications` with `{user_id, todo_id, message, created_at, read_at=null}`. The job is idempotent — if it runs twice for the same `(todo_id, due_at)` it must not produce duplicate notifications. This is enforced by a unique index on `(todo_id, due_at_snapshot)` in the notifications table.

When a todo is updated such that `due_at` changes, the previously scheduled job for that todo is removed and a new one is scheduled. When a todo is deleted or marked complete, its pending reminder is cancelled. Cancellation is best-effort and idempotent — if the job already fired, the existing notification is left in place (a completed todo can still surface a "this was due" reminder, which is acceptable; documented as a known behavior).

If the server restarts, scheduled jobs survive because they live in the Postgres-backed job store (APScheduler's `SQLAlchemyJobStore`). Jobs whose fire time passed during downtime fire on startup ("misfire grace time" configured to a reasonable bound, e.g., 1 hour).

### 4.4 In-app notifications

A `GET /notifications` endpoint returns the current user's notifications (newest first, paginated by simple `limit/offset`, default 50). `POST /notifications/{id}/mark-read` sets `read_at`. The frontend has a "Notifications" view that polls this endpoint every 30 seconds while open and shows unread count.

### 4.5 UI requirements

A login/register screen, a main todo list view (with create-todo form inline), per-todo controls (toggle complete, edit, delete), a notifications panel, and a clear signed-in/signed-out state in the header. The UI shows server-side validation errors next to the offending field and uses optimistic updates for the complete-toggle (rolling back on error).

## 5. Non-Functional Requirements

**Security.** Passwords hashed with bcrypt (cost ≥ 12). Session credential is an opaque UUID in an `HttpOnly`, `Secure` (production), `SameSite=Lax` cookie — not readable by JavaScript, not attachable on cross-site requests. Session validity is checked server-side on every request, so logout invalidates the credential immediately. All inputs validated server-side with Pydantic. SQL via SQLAlchemy parameterized queries — no string concatenation. CORS restricted to the frontend origin with `Access-Control-Allow-Credentials: true` so the cookie can flow. No secrets in logs (session IDs are not logged at info level).

**Reliability.** Reminder jobs are persistent (survive restart) and idempotent (safe to re-run). Database access uses transactions for any multi-statement write. Background-job failures are logged with traceback and do not crash the scheduler.

**Performance.** N+1 queries avoided on the todo list endpoint. The list endpoint paginates (default 50). All indexes are explicit: `todos(user_id, due_at)`, `notifications(user_id, created_at DESC)`, `notifications UNIQUE(todo_id, due_at_snapshot)`.

**Observability.** Structured logs with request ID, user ID (when authenticated), and outcome. Background jobs log start, success, and failure with the same request ID propagated via job kwargs.

**Local-run usability.** `docker compose up` brings up Postgres; `make dev` or documented `npm run` + `uvicorn` commands start frontend and backend. Seed data and a test account are documented in the README.

## 6. Data Model (initial cut)

```
users:           id (uuid pk), email (citext unique), password_hash, created_at
sessions:        id (uuid pk), user_id (fk users), expires_at (timestamptz),
                 created_at, last_used_at, revoked_at (timestamptz nullable)
                 INDEX(user_id), INDEX(expires_at)
todos:           id (uuid pk), user_id (fk users), title, description,
                 completed (bool), due_at (timestamptz nullable),
                 created_at, updated_at
notifications:   id (uuid pk), user_id (fk), todo_id (fk),
                 due_at_snapshot (timestamptz), message,
                 created_at, read_at (nullable)
                 UNIQUE(todo_id, due_at_snapshot)
apscheduler_jobs (managed by SQLAlchemyJobStore — no app schema work)
```

## 7. Critical-Path Test Targets

The brief requires tests on at least one critical path. The two paths most worth defending in the interview:

1. **Auth + ownership isolation.** Register two users, create a todo as A, attempt every read/write on it as B, expect 404. Verifies the boring-but-critical bug class.
2. **Reminder scheduling lifecycle.** Create a todo with `due_at = now + 20m`, assert a job exists with the right fire time; update `due_at`; assert the old job is gone and a new one exists; delete the todo; assert no job remains. Then force-run the job and assert exactly one notification row.

If time allows: a happy-path E2E with the React app (Playwright or React Testing Library).

## 8. Success Criteria

The submission is considered complete when:

- A fresh clone runs locally following only the README, with no missing-secret or missing-step failures.
- All endpoints listed above respond correctly to a manual smoke test (auth, CRUD, list, complete, delete, due-date reminder fires).
- Ownership-isolation and reminder-lifecycle tests pass.
- The README explains the architecture in a few paragraphs and is honest about which parts of the code were AI-drafted, which were modified, and where the candidate disagreed with AI suggestions.
- The candidate can walk through any file in the interview and explain the design choices.

## 9. Risks & Mitigations

The biggest risks are scope creep (the brief explicitly warns: a complete simple solution beats an incomplete ambitious one — mitigate by ruthlessly cutting the "could have" list if behind), reminder correctness under edits (mitigated by the snapshot column + unique index, and by tests covering update/delete/complete), and session-handling pitfalls (mitigated by the `HttpOnly` + `Secure` + `SameSite=Lax` cookie config, server-side expiry checks on every request, and a `revoked_at` column for immediate logout).

A second-order risk is over-relying on AI output for the auth flow; the candidate should hand-write the password hashing, session creation, and cookie-setting code (or at least review it character by character) since these are the most-asked-about lines in the interview. The session-cookie config in particular has small flags with large security consequences (`HttpOnly`, `Secure`, `SameSite`, `Max-Age`, `Path`) — each one should be defensible.
