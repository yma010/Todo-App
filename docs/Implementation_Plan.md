# Implementation Plan — Todo App with Due-Date Reminders

**Stack:** FastAPI (Python 3.12) · APScheduler (in-process, Postgres job store) · PostgreSQL 16 · React 18 + Vite
**Target time budget:** 3–4 hours active build, including tests and README
**Companion doc:** `PRD.md`

---

## 0. Why this stack (one-paragraph defense for the interview)

FastAPI gives async-first request handling, Pydantic validation as a first-class citizen, and OpenAPI docs for free — all things that matter for a production-minded full-stack exercise. APScheduler in-process with a `SQLAlchemyJobStore` is the lightest credible answer for background jobs: it survives restart, supports misfire policies, and avoids dragging in a broker (Redis) and a worker process for a 2–4 hour exercise. Postgres over SQLite because the brief tests concurrency and async patterns — Postgres has the locking primitives needed to defend reminder correctness, and running it via Docker is one command. The bigger architecture (Celery + Redis + Postgres) is the right answer at scale; the plan calls this out explicitly in the README and explains the tradeoff.

## 1. Repo Layout

```
todo-app/
  docker-compose.yml          # postgres only
  Makefile                    # dev shortcuts
  README.md
  backend/
    pyproject.toml
    .env.example
    alembic.ini
    alembic/
      versions/
    app/
      main.py                 # FastAPI app + lifespan (scheduler start/stop)
      config.py               # Pydantic Settings, env-driven
      db.py                   # SQLAlchemy engine + session
      models.py               # User, Session, Todo, Notification
      schemas.py              # Pydantic request/response models
      security.py             # password hashing, session create / lookup / revoke
      deps.py                 # get_current_user, get_db
      scheduler.py            # APScheduler init + job functions
      routers/
        auth.py
        todos.py
        notifications.py
    tests/
      conftest.py
      test_auth_isolation.py
      test_reminders.py
  frontend/
    package.json
    vite.config.ts
    src/
      api.ts                  # fetch wrapper, credentials: "include"
      auth/AuthContext.tsx
      pages/Login.tsx
      pages/Todos.tsx
      pages/Notifications.tsx
      components/TodoItem.tsx
      components/TodoForm.tsx
      App.tsx
      main.tsx
```

## 2. Phased Build

### Phase 1 — Bootstrap & infra (≈25 min)

Create the repo, `docker-compose.yml` for Postgres, a `Makefile` with `make db`, `make api`, `make web`, `make test`. Initialize the FastAPI app with a `/healthz` endpoint, wire SQLAlchemy + Alembic, generate the initial migration with empty models so the apscheduler tables also live in this DB. Scaffold the Vite + React + TypeScript frontend with a single placeholder page that calls `/healthz` and renders the JSON. **Exit criteria:** `docker compose up` then `make api` then `make web` brings up a working empty-shell app reachable on `http://localhost:5173`.

### Phase 2 — Models & migrations (≈25 min)

Define `User`, `Session`, `Todo`, `Notification` SQLAlchemy models per the data model in the PRD. Add indexes: `sessions(user_id)`, `sessions(expires_at)` (used by the cleanup query), `todos(user_id, due_at)`, `notifications(user_id, created_at DESC)`, `UNIQUE(todo_id, due_at_snapshot)` on notifications. Use `citext` for `users.email` (extension enabled in migration). Generate and apply the Alembic migration. **Exit criteria:** `alembic upgrade head` is clean; `\dt` shows all four tables; constraint violations behave as expected via a quick `psql` smoke test.

### Phase 3 — Auth (server-side sessions, ≈75 min)

This phase replaces the original JWT-in-memory design with **server-side sessions + httpOnly cookie**. See README §"Auth: Sessions vs JWT" for the disagreement that produced this choice; the short version is that JWT in JS memory is exposed to XSS exfiltration and is not production-ready, which is one of the explicit axes the brief tests.

**`security.py` — three small functions and zero JWT.**

- `hash_password(plain) -> str` using `passlib.context.CryptContext(schemes=["bcrypt"])` with cost 12.
- `verify_password(plain, hashed) -> bool`.
- `create_session(db, user_id) -> Session` inserts a `sessions` row with `id = uuid4()`, `expires_at = now + SESSION_EXPIRES_DAYS`, `created_at = now`, `last_used_at = now`, `revoked_at = None`. Returns the row so the caller can read `.id` for the cookie.
- `lookup_session(db, session_id) -> Session | None` returns the row only if it exists, `expires_at > now`, and `revoked_at is None`. Touches `last_used_at` and commits.
- `revoke_session(db, session_id)` sets `revoked_at = now` and commits.

**Endpoints.**

- `POST /auth/register` — validates email + password via Pydantic (`min_length=12` on password, `EmailStr` for email), hashes the password, inserts the `User`, calls `create_session`, sets the cookie on the response, returns `{"user": {...}}` (no credential in the body). 201 on success, 409 on duplicate email.
- `POST /auth/login` — looks up user by email, verifies password (constant-time via `passlib`), `create_session`, sets the cookie, returns user info. 401 on bad credentials with a generic message — do not leak whether the email exists.
- `POST /auth/logout` — reads the cookie, calls `revoke_session`, clears the cookie via `response.delete_cookie(...)`. 204 on success. Idempotent: still returns 204 if there was no valid session.
- `GET /auth/me` — returns the current user; convenient for the frontend to check auth state on mount.

**The cookie config — every flag is defensible.**

```python
response.set_cookie(
    key=settings.SESSION_COOKIE_NAME,   # "todo_session"
    value=str(session.id),               # opaque UUID, no claims
    max_age=settings.SESSION_EXPIRES_DAYS * 24 * 3600,
    httponly=True,                       # JS cannot read → XSS-safe
    secure=settings.COOKIE_SECURE,       # True in prod, False in dev (HTTP)
    samesite="lax",                      # mitigates CSRF on cross-site nav
    path="/",
)
```

`HttpOnly` is the headline flag: even if an attacker injects JavaScript into the page (XSS), it cannot read the cookie. `Secure` is required in production to prevent the cookie traveling over plaintext HTTP; gated to `False` in dev where the server runs on `http://localhost`. `SameSite=Lax` makes the browser refuse to attach the cookie to most cross-origin requests, which kills the common CSRF vectors without requiring a separate CSRF token endpoint for an MVP. `Path=/` scopes the cookie to the whole app; `Max-Age` matches the session expiry so a deleted server-side row and a stale client cookie don't drift.

**`deps.get_current_user`.**

Reads `request.cookies.get(SESSION_COOKIE_NAME)`. If missing, raises 401. Calls `lookup_session`. If `None` (expired or revoked), raises 401 *and* clears the cookie on the response so the client doesn't keep sending a dead credential. Loads the user via `db.get(User, session.user_id)`, returns it. Every protected endpoint depends on this, so the user-id used in queries is always trustworthy.

**Frontend changes from the original plan.**

`fetch` calls must include `credentials: "include"` so the browser actually attaches the session cookie. The Vite dev server's `/api` proxy is already same-origin from the browser's perspective (`localhost:5173 → localhost:5173/api → localhost:8000`), so no CORS preflight gymnastics. The backend's CORS middleware sets `allow_credentials=True` and a single explicit origin (`http://localhost:5173`) — wildcard origin is incompatible with credentialed requests and would silently break the cookie.

The frontend's `AuthContext` now calls `GET /auth/me` on mount to determine auth state (the cookie may already be present from a prior session). `login`/`register` POST and on success refresh from `/auth/me`. `logout` POSTs to `/auth/logout` and clears local React state. There is no token in JS at any point.

**Things to be ready to defend in the interview.**

Why sessions over JWT — revocation works, no signing-key management, opaque UUID leaks no information. Why bcrypt cost 12 — current OWASP-aligned guidance; argon2id is also acceptable but bcrypt is more universally understood. Why `SameSite=Lax` rather than `Strict` — Strict breaks normal navigation flows (clicking a link from email to the app would log the user out); Lax keeps that working while still blocking the CSRF vectors that matter. Why no CSRF token endpoint — `SameSite=Lax` covers the common cases for state-changing requests; a token endpoint is the next step at scale or when supporting older browsers. Why 14-day expiry — UX tradeoff; could be tightened with a "remember me" toggle, but that's stretch.

**Exit criteria.** Register + login via curl with `-c cookies.txt` / `-b cookies.txt` round-trips successfully; `GET /api/todos` is 401 without the cookie file and 200 with it; logout is 204 and the same cookie file then returns 401. Inspecting the cookie in DevTools shows all four flags set correctly. The `sessions` table has rows being created on login and `revoked_at` being populated on logout.

### Phase 4 — Todos CRUD with strict ownership (≈40 min)

Implement the five todo endpoints (`GET /todos`, `POST /todos`, `GET /todos/{id}`, `PATCH /todos/{id}`, `DELETE /todos/{id}`) and the two notification endpoints (`GET /notifications`, `POST /notifications/{id}/mark-read`). Every query is filtered by `user_id = current_user.id`. Single-row lookups by id that don't match the user return 404 — not 403 — to avoid leaking row existence. Pydantic schemas enforce all field constraints (title length, description length, `due_at` is a future timestamp at create time).

Write a tiny in-process helper `get_or_404(db, model, id, user_id)` rather than copy-pasting filter logic across endpoints. **Exit criteria:** curl through every endpoint as user A and as user B; B can never see or mutate A's rows; validation errors return 422 with field-level detail.

### Phase 5 — Background scheduler (≈45 min)

Add APScheduler with `SQLAlchemyJobStore` pointing at the same Postgres DB. Start the scheduler in the FastAPI `lifespan` hook; shut it down cleanly on app exit. Define a job function `fire_reminder(todo_id, due_at_iso)` that:

1. Opens its own DB session (scheduler runs outside request scope).
2. Re-reads the todo; if missing or completed, returns silently (idempotent cancellation).
3. Re-reads the todo's current `due_at`; if it no longer matches `due_at_iso`, returns silently (stale job).
4. Inserts a row into `notifications`. The `UNIQUE(todo_id, due_at_snapshot)` index catches double-fire — wrap the insert in a try/except for `IntegrityError`, log, swallow.

Wire creation/update/delete handlers to schedule/reschedule/remove jobs. Use job IDs of the form `reminder:{todo_id}` so reschedule is a `scheduler.add_job(..., replace_existing=True)` one-liner. Misfire grace time: 1 hour. Lead time before `due_at`: configurable via `REMINDER_LEAD_SECONDS` env, default 900.

The four things to be ready to defend in the interview: persistence across restart, idempotency, cancellation correctness, and the race between an update mid-fire (mitigated by the re-read in step 3 plus the unique index in step 4).

**Exit criteria:** create a todo with `due_at = now + 60s` and `REMINDER_LEAD_SECONDS=30`; wait; observe a notification row; delete a todo before its reminder fires and confirm no row appears; restart the app between schedule and fire and confirm the job still runs.

### Phase 6 — Frontend (≈50 min)

Three pages and a context. `AuthContext` holds the **user object** (not a token) in React state and exposes `login`, `register`, `logout`, plus an initial `GET /auth/me` call on mount to hydrate from an existing session cookie. `api.ts` is a small `fetch` wrapper that sets `credentials: "include"` on every request so the browser attaches the session cookie, and throws on non-2xx. The `Todos` page lists todos (newest-first, with the next-due item highlighted), an inline create form, and per-row controls (checkbox to toggle complete, edit-in-place title and due-date, delete). The `Notifications` page lists notifications and lets the user mark them read; polls every 30s. The header shows the unread count.

Optimistic update on the complete-toggle: flip immediately, send the PATCH, roll back on error with a small inline error message. Validation errors from the server (422) get rendered next to the offending field.

**Exit criteria:** create-edit-complete-delete flows work; due dates round-trip correctly; refreshing the page preserves login (or cleanly forces re-login if expired); notifications appear within 30s of firing.

### Phase 7 — Tests (≈25 min)

`tests/conftest.py` spins up a Postgres test DB (via a fixture that creates a schema per test session) and a FastAPI `TestClient`. Two test files:

- `test_auth_isolation.py` — register A and B (each in its own `TestClient` so each gets its own cookie jar); A creates a todo; B receives 404 on GET/PATCH/DELETE for A's todo id; B's list does not include A's todo. Additionally: unauthenticated requests get 401; after `POST /auth/logout`, the same client gets 401 (verifies server-side session revocation actually invalidates the credential).
- `test_reminders.py` — create a todo with `due_at = now + 10m`; assert a job with id `reminder:{todo_id}` exists with the expected next-run time; PATCH `due_at` to `now + 20m`; assert the job's next-run advanced; DELETE the todo; assert the job is gone. Then create another todo, force-fire the job via `scheduler.modify_job(next_run_time=now)`, wait, assert a notification row; force-fire again, assert still only one row (idempotency).

**Exit criteria:** `pytest` is green; tests run against a real Postgres test DB.

### Phase 8 — README & polish (≈25 min)

The README covers: prerequisites, `docker compose up` → `alembic upgrade head` → `uvicorn ...` → `npm run dev`, a `.env.example` walkthrough, the demo account or the register flow, the architecture in a few paragraphs (auth model, ownership pattern, reminder lifecycle, where the scheduler lives, what the indexes do), and a candid **AI Usage** section.

The AI Usage section names which AI tool was used, lists where AI was useful (scaffolding, Pydantic schemas, boilerplate test fixtures), and — most importantly — lists at least three places where the candidate disagreed with AI output and changed direction. Example candidate disagreements to surface honestly:

- AI initially proposed JWT in React memory as a "demo-budget" shortcut; rejected because it's exposed to XSS exfiltration and is not production-ready, which is exactly what the brief tests. Switched to server-side sessions + httpOnly+Secure+SameSite=Lax cookie. See README §"Auth: Sessions vs JWT" for the full reasoning.
- AI suggested catching `Exception` broadly in the reminder job; narrowed to `IntegrityError` and let everything else log + bubble.
- AI suggested 403 for cross-user access; switched to 404 to avoid leaking row existence.
- AI suggested a "fire job synchronously inside the request" shortcut; rejected because it defeats the point of the exercise.

Also include a short "What I'd do next" list mapping to the PRD's "could have" items.

## 3. End-to-End Smoke Script (manual, pre-submit)

A flat sequence to run before declaring done: register A, register B, log in as A, create a todo with no due date, create a todo with `due_at = now + 90s` and `REMINDER_LEAD_SECONDS=30`, observe a notification within ~60s. Restart the API. Log in as B; confirm B sees neither todo and gets 404 on direct GET. Update A's due-dated todo to push the due date by 5 minutes; confirm no notification fires at the original time. Delete A's other todo. Complete the remaining one. Mark the notification read. Log out.

## 4. Risks Re-Stated, With Mitigation Tied to Phases

Scope creep: phases 1–7 are the bar; if any phase blows its budget, cut from phase 6 ("could have" UI) before cutting tests. Reminder correctness under edits: covered by phase 5 (snapshot column, re-read, unique index) and phase 7 (lifecycle test). AI-output overreliance: phase 3 is hand-written/line-reviewed, and the README's AI section forces explicit disagreements on the record. Hidden secrets risk: `.env.example` only, `.gitignore` includes `.env`, all secrets loaded via `Settings`, never printed; session IDs not logged at info level.

## 5. Definition of Done (checklist)

- Fresh clone → README steps → app runs.
- Register + login + CRUD + complete + delete work in the UI.
- Reminder fires and produces exactly one notification per `(todo_id, due_at)`.
- Reminder cancels on delete/complete and reschedules on due-date change.
- Ownership-isolation and reminder-lifecycle tests pass.
- No secrets in repo; `.gitignore` covers `node_modules`, `__pycache__`, `.env`.
- README has architecture explanation and honest AI-usage section.
- Candidate can open any file at random and explain it.
