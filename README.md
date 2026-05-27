# Todo App with Due-Date Reminders

[![CI](https://github.com/yma010/Todo-App/actions/workflows/ci.yml/badge.svg)](https://github.com/yma010/Todo-App/actions/workflows/ci.yml)

A small but production-minded full-stack todo app:

- **Backend:** FastAPI (Python 3.12) + SQLAlchemy 2 + Alembic
- **Database:** PostgreSQL 16 (Docker)
- **Background jobs:** APScheduler with a Postgres-backed job store (`SQLAlchemyJobStore`)
- **Frontend:** React 18 + Vite + TypeScript
- **Auth:** server-side sessions in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie

See [`docs/Interview_exercise.md`](docs/Interview_exercise.md) for the
exercise brief, [`docs/PRD.md`](docs/PRD.md) for the product requirements,
[`docs/Implementation_Plan.md`](docs/Implementation_Plan.md) for the
phased build plan, and [`docs/README_notes.md`](docs/README_notes.md) for
the long-form architecture decisions this section summarizes.

---

## Prerequisites

- **Docker** (for Postgres) — Docker Desktop or Docker Engine
- **uv** (manages Python 3.12 and Python deps) — install with
  `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Node 20+** and npm

## Quick start

```bash
# 1. Start Postgres
make db

# 2. Install Python + JS deps (uv auto-installs Python 3.12 if needed)
make install

# 3. Apply database migrations
cp backend/.env.example backend/.env       # uses sane defaults; edit if needed
make migrate

# 4. Run the API (terminal 1) and the web app (terminal 2)
make api    # → http://localhost:8000
make web    # → http://localhost:5173
```

Open <http://localhost:5173>. Register an account (password must be ≥12
characters), then add a todo with a due time a minute or two from now. To
see a reminder fire quickly, start the API with a short lead time:

```bash
REMINDER_LEAD_SECONDS=2 make api
```

## Tests

```bash
make test
```

Tests live in `backend/tests/` and require Postgres to be up (`make db`).
The suite covers the two critical paths called out in the PRD — cross-user
data isolation and the reminder scheduling lifecycle (schedule, reschedule,
cancel on delete/complete/clear, idempotent fire) — plus the defense-in-depth
layers added on top (cookie clearing on 401, Origin enforcement on mutating
routes, per-IP throttle + log emission, security headers, prod fail-closed
validator, and docs-route gating). 43 tests across five files; see the
repository layout below for what each file covers.

## Repository layout

```
backend/
  app/
    main.py            FastAPI app + lifespan; origin-check + security-headers middleware
    config.py          Pydantic Settings (env-driven) + validate_for_env()
    db.py              SQLAlchemy engine + session factory
    models.py          User, Session, Todo, Notification
    schemas.py         Pydantic request/response models
    security.py        bcrypt + session create/lookup/revoke
    deps.py            get_current_user dependency
    rate_limit.py      in-process sliding-window limiter
    scheduler.py       APScheduler init + fire_reminder job
    routers/
      auth.py          /api/auth/{register,login,logout,me} + per-IP throttle + WARN logs
      todos.py         /api/todos CRUD
      notifications.py /api/notifications + mark-read
  alembic/             schema migrations
  tests/
    conftest.py
    test_auth_isolation.py    session lifecycle, isolation, password rules, cookie clearing
    test_csrf.py              Origin-header enforcement on mutating routes
    test_rate_limit.py        throttle behavior + log emission
    test_reminders.py         scheduler lifecycle + idempotency
    test_security_headers.py  prod fail-closed validator + headers + docs gating
frontend/
  src/
    api.ts             fetch wrapper (credentials: include)
    auth/AuthContext.tsx
    pages/{Login,Todos,Notifications}.tsx
    components/{TodoForm,TodoItem}.tsx
docker-compose.yml     Postgres only
Makefile               dev shortcuts
```

---

## Architecture

### Auth: server-side sessions, opaque cookie

When a user registers or logs in, the server inserts a row into the
`sessions` table — `id` is a UUID, plus `user_id`, `expires_at`,
`created_at`, `last_used_at`, and a nullable `revoked_at` — and sets a
cookie whose value is the opaque session UUID. The cookie carries no user
data and no claims.

Every flag on the cookie is intentional:

| Flag | Purpose |
| --- | --- |
| `HttpOnly` | JavaScript cannot read the cookie → XSS cannot exfiltrate the credential. |
| `Secure` | Cookie travels only over HTTPS in production (gated to `false` in dev where the server is `http://localhost`). |
| `SameSite=Lax` | Browser refuses to attach the cookie on most cross-site requests → CSRF mitigated without a separate token endpoint. `Lax` (not `Strict`) so that clicking a link from email back to the app doesn't force re-login. |
| `Path=/` | Cookie applies to the whole app. |
| `Max-Age` | Matches `SESSION_EXPIRES_DAYS` so a deleted server row and a stale client cookie don't drift. |

`get_current_user` (`backend/app/deps.py`) reads the cookie, looks up the
session row, rejects the request if missing/expired/revoked, touches
`last_used_at`, and returns the `User`. **The user id is always read from
the session row — never from the request body.**

Because validity is checked on every request, logout is immediate and
complete: `revoke_session` sets `revoked_at = now()`, and the next request
fails the lookup. This is the property a stateless JWT loses without a
separate denylist.

### Reminders: persistent, idempotent, cancellable

APScheduler runs inside the FastAPI process with a `SQLAlchemyJobStore`
that writes jobs into the same Postgres database as the app data. Two
properties matter:

1. **Persistence across restart.** Jobs live in `apscheduler_jobs`; if the
   web process dies, the schedule survives. `misfire_grace_time` is set
   to one hour so a reminder for "ten minutes ago" still surfaces when
   the process comes back, while a reminder from yesterday is skipped as
   stale noise.
2. **Idempotency at the database level.** The `notifications` table has
   `UNIQUE(todo_id, due_at_snapshot)`. The fire job wraps its `INSERT` in
   `try/except IntegrityError` and swallows duplicates. So however many
   times the job runs — APScheduler retry, hand-replay, race against a
   restart — the user sees exactly one notification per
   `(todo_id, due_at)` pair.

The job also re-reads the todo before inserting and skips silently if the
todo was deleted, completed, or had its `due_at` changed while the job
was sitting in the store. This handles the edit-mid-fire race cleanly.

### Cross-user isolation

Every read and write filters by `user_id = <current_user>`. Single-row
lookups that don't match return **404, not 403** — this avoids leaking
the existence of other users' rows by id-guessing. The pattern is
centralized in `_get_owned_or_404` in `backend/app/routers/todos.py`.

### Validation

Pydantic enforces all field constraints server-side (title 1–200 chars,
description ≤2000, password ≥12, email syntactic validity). 422 responses
include field-level detail so the frontend can render the right error
next to the right input.

### Password rules

A minimum-length check is necessary but not sufficient — a 12+ character
string of sequential digits trivially passes a length-only rule. The
register endpoint enforces three character-class rules:

- length ≥ 12
- at least one digit (`0-9`)
- at least one symbol (anything that is not `[A-Za-z0-9]`)

Every rejection returns the same fixed 422 response, regardless of which
rule tripped:

```
Invalid password. Must be at least 12 characters and include at least
one number and one symbol.
```

The vagueness is intentional — telling the caller *which* specific rule
failed ("too short" vs. "no digit") helps an attacker calibrate against
the policy. The message still tells a legitimate user exactly how to
construct a valid password, and the same string appears in the register
form as helper text so the requirements are visible up front.

The rules are enforced server-side in
`security.validate_password` (`backend/app/security.py`); the frontend
hint is a UX aid only — never a substitute.

### Registration error ordering

`POST /api/auth/register` runs checks in this order:

1. **Email already registered → 409.** Returned even if the password is
   invalid, so a user retrying with the same email doesn't get sent
   through password debugging when the real problem is that they
   already have an account.
2. **Password fails the rules → 422** with the fixed message above.
3. Insert the user, create a session, set the cookie.

(We're aware that step 1 exposes a user-enumeration signal. The PRD's
explicit "log in vs. register" UX makes that signal an accepted
trade-off for this exercise; the production answer is a generic
"check your email for next steps" flow.)

### Security hardening (defense in depth)

These layers sit on top of the auth/session design above. Each defends
against a separate failure mode — the goal is that no single
misconfiguration breaks the whole story.

- **Cookie clearing on logout and 401.** `logout` and `get_current_user`
  return a `Set-Cookie` deletion header on the actual response (not a
  mutated injected `Response` that FastAPI's exception handler would
  silently drop). So `revoke_session` + the cleared cookie together
  mean the browser stops sending a dead credential immediately.
- **Origin check on state-changing routes.** A middleware in `main.py`
  rejects any `POST/PUT/PATCH/DELETE` whose `Origin` header is present
  and doesn't match `FRONTEND_ORIGIN` (including `Origin: null` from
  sandboxed iframes). Missing `Origin` is allowed so curl / TestClient
  / server-to-server still work; `SameSite=Lax` covers the browser CSRF
  case. This is defense in depth — if the cookie's `SameSite` is ever
  relaxed (e.g. for a future subdomain), the API doesn't silently open.
- **Per-IP auth throttle + structured failure logs.** A small
  sliding-window limiter (`app/rate_limit.py`, single worker only)
  caps `/auth/login` at 10/min and `/auth/register` at 5/10min per
  client IP, returning `429` with `Retry-After`. Failed logins, register
  conflicts, and throttle hits all log at WARN via the `todo.auth`
  logger. Emails are logged as a 16-char SHA-256 fingerprint
  (`email_fp=…`), never plaintext — so log volume tells you about
  attacks without disclosing accounts.
- **Baseline security response headers.** Every response carries
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and
  `Strict-Transport-Security: max-age=63072000; includeSubDomains`.
  Every `/api/*` response also carries `Cache-Control: no-store` so
  user-private data can't sit in shared/intermediary caches.
- **Prod fail-closed config.** `Settings.validate_for_env()` runs in
  the FastAPI `lifespan`. When `ENV=prod`, the app refuses to start
  unless `COOKIE_SECURE=true` and `FRONTEND_ORIGIN` starts with
  `https://`. All problems surface in a single error so a misconfigured
  deploy doesn't require multiple re-deploy cycles to find them.
- **Auto-docs gated to dev.** `/docs`, `/redoc`, and `/openapi.json`
  are reachable in dev for ergonomics, and disabled (404) when
  `ENV=prod` so the API surface map isn't free reconnaissance.
- **Bound to localhost by default.** `docker-compose` publishes
  Postgres on `127.0.0.1:5432` (not LAN-wide); `make api` binds
  uvicorn to `127.0.0.1`. An explicit `make api-lan` target opts in to
  `0.0.0.0` for testing from another device on a trusted network.

New env vars introduced by these layers (all have safe defaults in
`backend/.env.example`):

| Var | Default | Purpose |
| --- | --- | --- |
| `ENV` | `dev` | Set to `prod` to trigger the fail-closed validation and disable auto-docs. |
| `AUTH_LOGIN_MAX_PER_MIN` | `10` | Per-IP cap on `/api/auth/login`. |
| `AUTH_REGISTER_MAX_PER_10MIN` | `5` | Per-IP cap on `/api/auth/register`. |

The two layers we knowingly didn't add: per-account login throttle
(would let an attacker DoS a single user by spamming failed
attempts — needs a lockout-vs-DoS product decision) and a "revoke all
other sessions" endpoint (needs UI work). Both are on the "would do
next" list.

---

## Architecture decision: APScheduler vs Celery

For this exercise, APScheduler with a Postgres job store is the right
answer. The scope is small — the background work is "insert one row" —
and Celery would mean running a Redis broker as a separate process plus
a Celery worker as another, all to schedule one-shot date jobs. The
in-process scheduler keeps the deploy story to "one web process + one
Postgres." The job store goes into Postgres (not in-memory) because
losing every scheduled reminder on restart would be a real correctness
bug.

The known ceiling: a single APScheduler instance can only own a given
job store; the scheduler also competes with request handling for CPU and
memory. At scale, or once the background work involves real email/SMS
delivery, the migration is straightforward: move the reminder function
behind a Celery task and call `send_reminder.delay(...)` from the
endpoint instead of `scheduler.add_job(...)`.

A second known limitation: APScheduler does not automatically retry a
job that started executing and crashed before completing. The unique
index makes any retry *safe* (no duplicates) but doesn't make a lost
fire *recoverable*. Celery with `acks_late=True` is the production
answer.

---

## Auth: where I disagreed with AI

AI initially recommended **JWT in React `useState`** as a "scope-fit"
shortcut and listed the limitations (lost on tab close, no revocation
without a denylist) as acceptable demo-time tradeoffs. I rejected this
for two reasons:

1. **The brief explicitly tests production-mindset alongside security.**
   A choice that has to be defended as "fine for a demo, not for
   production" is exactly the kind of choice an experienced reviewer
   flags.
2. **JWT in JS memory is exposed to XSS exfiltration.** Any token JS can
   read can be read by an attacker who manages to inject script onto the
   page. The XSS-defensive position is to store the credential in a
   place JavaScript cannot reach — i.e., an `HttpOnly` cookie.

The real options:

- **JWT in HttpOnly cookie** — XSS-safe but no revocation without a denylist.
- **Server-side sessions + HttpOnly cookie** — XSS-safe *and* revocable. A small `sessions` table is the entire cost.
- **Refresh/access token pattern** — production-grade SPA standard, but the right scope for a real app with real OAuth, not a 4-hour exercise.

I picked server-side sessions. Every property I care about works out of
the box: logout invalidates immediately, the table can carry audit
context, and the migration path to Redis-backed sessions if I need
horizontal scaling doesn't touch application code.

The interview soundbite: *server-side sessions with an `HttpOnly`,
`Secure`, `SameSite=Lax` cookie containing an opaque UUID. JS can't read
the credential so XSS can't exfiltrate it; the browser refuses to attach
the cookie on most cross-site requests so CSRF is mitigated without a
separate token; logout invalidates the row so revocation is immediate.*

## Other places I disagreed with AI

- **AI suggested catching `Exception` broadly in the reminder job.** I narrowed it to `IntegrityError` (the dedup path) and let everything else log with traceback and bubble. Swallowing all exceptions silently hides correctness bugs.
- **AI suggested returning 403 for cross-user access.** I switched to 404 — returning 403 leaks the existence of the row.
- **AI suggested firing the reminder synchronously inside the request as a "demo shortcut."** Rejected — that defeats the point of the background-job exercise; the brief is explicit that async patterns are one of the things being tested.
- **AI's initial password validation was `min_length=12` only.** I noticed that this lets sequential-digit strings like `123456789101112` through, which is exactly the class of password the rule was meant to catch. First tried zxcvbn with score ≥ 3; the per-rule feedback ("This is similar to a commonly used password") was both wordy and a calibration signal for attackers. Settled on deterministic character-class rules (length, digit, symbol) with a single fixed error message that doubles as the construction hint — predictable for users, no per-rule disclosure to attackers.
- **AI ordered the register endpoint with password validation before the email-uniqueness check.** This meant a user retrying with an already-registered email kept getting password errors instead of "this email is registered." Swapped the order: email-exists fires first as 409, password validation second as 422, then insert.
- **AI's original logout / 401 code mutated FastAPI's injected `Response` and then either returned a fresh `Response()` or raised `HTTPException`.** The cookie-clearing `Set-Cookie` header was silently dropped in both cases — server-side revocation worked, but the browser kept re-sending a dead cookie until natural expiry. The "logout immediately invalidates the credential" claim in the architecture section was only half-true. Fixed by building the response object explicitly in `logout` and by attaching the deletion header via `HTTPException(headers=...)` in `get_current_user`. Two new tests now assert the `Set-Cookie` header is present and well-formed on the actual response.

---

## What I'd do next

Mapped to the PRD's "could have" list and the gaps above:

- In-app toast / bell when a notification arrives (currently polled every 30s)
- Snooze action that reschedules the reminder
- A daily cleanup job that deletes expired `sessions` rows
- Switch background work to Celery + Redis with `acks_late=True` for at-least-once delivery and automatic retry on mid-execution crashes
- Server-sent events instead of polling for the notifications list
- A small Playwright happy-path E2E to complement the API tests
- Per-account login throttle (in addition to the per-IP cap) — needs a deliberate lockout-vs-DoS product decision before shipping
- A `/auth/sessions` listing endpoint + "sign out of all other devices" UI, backed by the existing `sessions.revoked_at` column
- Swap the in-process rate limiter for a Redis-backed one when the deployment moves past a single worker

---

## AI usage

This project was built with assistance from Claude (Anthropic). AI was
useful for: scaffolding boilerplate (Vite project, Alembic config,
Pydantic schema shapes), writing the test fixtures, and as a sounding
board on design tradeoffs. The places I rejected or rewrote AI output
are documented above under "where I disagreed."

The auth code — `security.py`, the cookie configuration in
`routers/auth.py`, and `deps.get_current_user` — was reviewed
character-by-character and the cookie flag choices are independently
defensible. The reminder fire path (`scheduler.fire_reminder`) and the
test for idempotency were written deliberately to make the safety
property visible at the file level.
