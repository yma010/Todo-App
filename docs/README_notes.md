# README Notes (working draft)

Snippets to fold into the final `README.md` during Phase 8 of the implementation plan.

---

## Architecture Decision: APScheduler vs Celery

We chose **APScheduler with a Postgres-backed job store** for this project, rather than the more conventional Celery + Redis setup.

**Why APScheduler here.** The scope is small — a single-user todo app where the background work is "insert one row into a notifications table" — and the brief specifically warns against over-engineering. Celery would mean running a Redis broker as a separate process, a Celery worker as another separate process, and dealing with task serialization. APScheduler runs inside the FastAPI process and uses a thread to fire scheduled jobs, which keeps the architecture to a single web process plus Postgres.

**Why we still persist jobs to Postgres.** APScheduler offers an in-memory job store, but we explicitly didn't use it — losing every scheduled reminder on a server restart would be a real correctness bug. The `SQLAlchemyJobStore` writes jobs into the same Postgres database as the application data, so reminders survive restart and the deploy story stays simple (no second persistence layer).

**What we'd change at scale.** If users grow, or if the background work expands to include real email/SMS delivery, signed-URL generation, or any heavier work, we'd move to Celery with Redis as the broker. The web process should not be doing heavy work on its own threads — it competes with request handling for CPU and memory, and the scheduler doesn't scale horizontally (only one APScheduler process can own a given job store at a time without extra coordination). The migration path is straightforward: the reminder function stays nearly identical; it just becomes a Celery task instead of an APScheduler job, and the endpoint calls `send_reminder.delay(...)` instead of `scheduler.add_job(...)`.

**Summary tradeoff.** Single-process simplicity now, in exchange for a known ceiling on background-work scale and throughput. The job-store-in-Postgres choice means we get persistence for free without adding Redis.

---

## Failure Modes & Reliability

This is a small app, but the design assumes the process can disappear at any moment. Crashes in production almost never come from the application's own logic — they come from the surrounding environment: a deploy sends `SIGTERM` mid-job, the container orchestrator evicts the pod, an OOM killer fires because of an unrelated memory leak, the database connection drops during a failover or network blip. Designing for "the todo logic is correct" is not the same as designing for "the process survives." The two are separate problems.

**How the design absorbs these failures**

*Idempotency via a unique index.* The `notifications` table has `UNIQUE(todo_id, due_at_snapshot)`. If a reminder job fires, inserts a notification, then crashes before APScheduler marks the job complete — and is later retried — the duplicate insert fails on the unique constraint. The job wraps the insert in a `try/except IntegrityError`, logs, and swallows. The user sees exactly one notification per `(todo_id, due_at)` pair regardless of how many times the job ran. Without this index, retry would produce duplicates.

*Persistent job store + misfire grace time.* APScheduler's `SQLAlchemyJobStore` keeps the schedule in Postgres, not in process memory. If the web process dies before a job's fire time, the job is still there when the process comes back. The `misfire_grace_time` setting (configured at ~1 hour) controls what happens to jobs whose fire time passed during downtime: late-but-recent jobs still fire, very stale ones are skipped. A reminder for "10 minutes ago" still surfaces when the server returns; a reminder from yesterday is dropped because a stale reminder is just noise.

*Re-read inside the job.* The job function re-reads the todo before inserting the notification. If the todo was deleted, completed, or had its due date changed while the job was sitting in the store, the job notices and exits silently. This handles the race between "user edits the todo" and "job fires" cleanly.

**Known limitation — crash mid-execution**

APScheduler does not automatically retry a job that started executing and then died before completing. Once the executor picks up a job, it's marked as dispatched. If the process crashes after the executor picked the job up but before the notification was inserted, that single notification is lost. The unique-index design means this is *safe* (no duplicates from any retry attempt elsewhere), but it is not *recoverable* without external help.

This is an accepted tradeoff for the exercise. At scale, the right tool is Celery with `acks_late=True` and a retry policy: the broker only acknowledges the task after the worker confirms success, so a crashed worker's task goes back on the queue for another worker to pick up. The migration path is direct — the job function changes very little; it just becomes a Celery task with retry decorators.

**Error logging**

The job body is wrapped in `try/except`. On exception, we log structured JSON to stdout with `todo_id`, `user_id`, `fire_time`, the exception class, and the traceback. Stdout logs are picked up by whatever log aggregator the host environment provides (Docker logs, CloudWatch, etc.). For SRE visibility at scale, a dedicated `job_failures` table would make failures queryable from the app itself — noted as a follow-up, not built here.

**Summary**

The reliability story is: idempotent inserts make retry safe, persistent storage makes restart safe, in-job re-reads make concurrent edits safe, and structured error logs make failures debuggable. The honest gap is automatic retry on mid-execution crash, which is where Celery would earn its keep.

---

## Auth: Sessions vs JWT (Where I Disagreed With AI)

This is one of the explicit "candidate disagreed with AI" entries the brief rewards. The exchange is worth recording in full because the reasoning matters more than the conclusion.

**What AI initially recommended.** A signed JWT (HS256, 60-minute expiry) returned in the login response body and held in React `useState`. The rationale offered was "smaller scope for a 4-hour exercise" — no session table, no cookie machinery, no CSRF concerns. AI flagged the limitations (token lost on tab close, server-side revocation requires a denylist) but framed them as acceptable demo-time tradeoffs.

**Where I pushed back.** Two problems:

1. **"Demo-time tradeoff" misses the bar.** The brief is explicit that production-mindset is one of the things being tested, alongside security as a named axis. A choice that has to be defended as "fine for the demo, not for production" is exactly the kind of choice an experienced reviewer flags. I've been criticized in past interviews for shipping auth shortcuts and explaining them away; I didn't want to repeat that pattern here.

2. **JWT in JS memory is exposed to XSS exfiltration.** Any token that JavaScript can read can be read by an attacker who manages to inject script onto the page — through a vulnerable dependency, a malformed user input that escaped sanitization, a third-party widget, anything. The "in-memory" framing is not a security improvement over `localStorage`; it's the same threat surface with worse UX. The actual XSS-defensive position is to store the credential in a place JavaScript cannot reach — i.e., an `HttpOnly` cookie.

**What I considered.** The real options I weighed:

- **JWT in `HttpOnly` cookie** — XSS-safe, but loses revocation. Logout cannot actually invalidate the credential until it expires unless I add a denylist; password change and "log me out everywhere" require the same denylist plumbing.
- **Server-side sessions + `HttpOnly` cookie** — XSS-safe and revocable. Slightly more code (a `sessions` table, expiry cleanup), but every production property I care about works out of the box: logout invalidates immediately, password change can nuke all sessions, the table can carry audit context.
- **Refresh + access token pattern** — production-grade SPA standard, but the right scope for a real app with real OAuth — not a 4-hour exercise.

**What I chose and why.** Server-side sessions in an `HttpOnly`, `Secure` (in production), `SameSite=Lax` cookie containing an opaque UUID. Reasoning:

- `HttpOnly` blocks XSS exfiltration of the credential. This is the headline security property.
- `SameSite=Lax` defeats the common CSRF vectors that exist when a browser will automatically attach cookies. Lax (not Strict) keeps "click a link from email to the app" working without re-login.
- `Secure` ensures the cookie never travels over plaintext HTTP in production. Gated to `false` in local dev where the server is `http://localhost`.
- Server-side validity check on every request means logout invalidates the credential immediately. No denylist needed. No JWT clock-skew weirdness.
- The opaque UUID leaks nothing — no user info, no expiry, no claims. The expiry lives in the `sessions` row, which the server controls.

**Cost.** ≈45 minutes over the JWT-in-memory plan. Absorbed by trimming stretch UI items in Phase 6.

**Limitations I'm not pretending don't exist.** Sessions are stateful — they don't scale to multiple backends without a shared store. The migration path is to move the session store from Postgres to Redis (or KeyDB) when latency or contention demands it; the application code doesn't change. Expired sessions accumulate in the table; for an MVP a daily cleanup job is sufficient (added to the "would do next" list), or a lazy `DELETE WHERE expires_at < now()` on a periodic schedule. CSRF tokens are not implemented because `SameSite=Lax` covers the common cases; a token endpoint is the next step if I add older-browser support.

**The interview soundbite.** *"Server-side sessions with an `HttpOnly`, `Secure`, `SameSite=Lax` cookie containing an opaque UUID. JS can't read the credential, so XSS can't exfiltrate it. The browser refuses to attach the cookie on most cross-site requests, so CSRF is mitigated without a separate token. Logout invalidates the session row, so revocation is immediate — which is the property JWT loses without a denylist. The migration path is moving the session store from Postgres to Redis if I need to scale."* Every flag is defensible, every property maps to a concrete threat.
