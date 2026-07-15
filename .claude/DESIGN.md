# DESIGN.md — Rate-Limited Async Job Queue

## Problem

Send transactional emails (order confirmations, OTPs, alerts) through a provider limited to
200 emails/minute. Bursts of ~2,000 requests can arrive in under 10 seconds. Need: no lost
jobs, no exceeding the rate limit, and safe recovery if a worker is killed mid-task.

## Architecture choice: Celery + Redis

| Option | Pros | Cons |
|---|---|---|
| Celery + Redis | Mature retry/backoff (`autoretry_for`, `retry_backoff`), `acks_late` + `task_reject_on_worker_lost` solve the crash-safety requirement directly, Redis already used for the rate limiter | More moving parts (broker + worker), larger config surface |
| Django-Q | Simpler, Django-native | Weaker retry ergonomics, less proven at bursty volume |
| Custom (asyncio + Redis) | Full control | Re-implements crash recovery / retry logic that Celery already solved |

**Chosen: Celery + Redis.** The reliability requirements map directly onto existing Celery
flags instead of custom crash-recovery code, and Redis is already needed for the rate limiter,
so no new infra.

## Rate limiter: sliding window (Redis sorted set)

Options were fixed window (INCR+EXPIRE), token bucket (DECR+TTL), sliding window (sorted set).

- **Fixed window** rejected: boundary burst problem — 200 requests at :59 and 200 at :01 is
  400 in 2 seconds even though each window individually stayed under 200.
- **Token bucket** rejected: refill needs extra timestamp math or a background job.
- **Sliding window** chosen: keeps a timestamped log in a Redis sorted set, prunes anything
  older than 60s, checks count before admitting. True rolling 200/60s, matches what "200/minute"
  actually means.

**Atomicity**: prune → count → conditionally add has to happen as one unit, or two workers can
both read "count is 199" and both proceed, blowing past 200. Done as a single Lua script
(`EVAL`) — Redis runs the whole script atomically, no other client's command can interleave.

**Redis failure**: fails **closed**. If Redis is unreachable, `allow()` returns `False` instead
of guessing. Reasoning: an ungoverned burst against the provider risks the API key getting
throttled/banned, which would block everything, not just this batch. Better to delay jobs than
risk that.

## Retry / backoff / dead-letter

- `autoretry_for=(RateLimitExceeded, Exception)`, `retry_backoff=True`, `retry_backoff_max=600`,
  `retry_jitter=True`, `max_retries=5`.
- Jitter matters because without it, many jobs rate-limited at the same instant would all retry
  at the same backoff intervals and re-create a burst against the limiter every time.
- Known trade-off: exponential backoff is built for transient failures, not steady-state
  throttling. A rate-limited job backs off exponentially even though the queue drains at a
  constant rate — some jobs wait longer than strictly necessary. Still correct (nothing lost,
  nothing exceeds the limit), just not the most efficient possible design.
- After `max_retries`, a custom `Task.on_failure` hook writes the job to a `DeadLetterJob` row
  (linked to the `EmailJob`) instead of letting it silently disappear — inspectable/replayable
  later.

## SIGKILL — what happens, and how this handles it

Default Celery acks a task **before** running it. If the worker is SIGKILL'd mid-task, the
broker already thinks it's done — job silently lost.

Fix: `CELERY_TASK_ACKS_LATE = True` — task is only acked after it finishes (success or
failure). SIGKILL mid-task means no ack ever reached the broker, so the task is redelivered to
another worker. Paired with `CELERY_TASK_REJECT_ON_WORKER_LOST = True`, which explicitly tells
Celery to reject (not drop) a task when its worker process disappears.

**Caveat**: `acks_late` on its own can cause a job to run twice — if the email was actually sent
right before the worker died, but the ack didn't make it back in time, the task gets redelivered
and looks like it never ran. Fixed with an `idempotency_key` on `EmailJob`: the task checks
`status == SENT` before sending anything, so a redelivered task recognizes it already did the
work and exits without a duplicate send. The idempotency key is generated once at submission
time (in `services.py`), not inside the task — generating it inside the task would produce a new
key on every redelivery and defeat the whole point.

## Testing

`notifications/tests.py`, run with `CELERY_TASK_ALWAYS_EAGER=True` (tasks run synchronously,
no need for a live worker, no `time.sleep()` anywhere):

1. **No job lost** — submit 500, assert 500 matching `EmailJob` rows exist.
2. **Rate limit never exceeded** — replay the Redis sorted set's timestamps after the run and
   check every possible 60s window across the whole timeline, not just the final count.
3. **Retry works** — mock the provider call to fail once then succeed; assert the job ends up
   `SENT` with `attempts >= 2`.
4. **Dead-letter works** — mock a permanent failure; assert the job ends up `FAILED` with a
   `DeadLetterJob` row.

## Known limitations / would revisit

- Windows dev requires `--pool=solo` or `--pool=eventlet` — the default `prefork` pool doesn't
  work reliably on Windows (multiprocessing/semaphore issues). Production (Linux) would use
  `prefork` normally.
- Upstash adds real network latency per rate-limit check vs. local Redis — fine at this volume,
  would reconsider for high-throughput production or fast CI.
- Redis TLS currently uses `ssl_cert_reqs=CERT_NONE` (encrypted, not cert-verified) — fine for
  this mock instance, would switch to `CERT_REQUIRED` with proper CA verification for production.
- Reverse-relation-style access patterns aren't a concern here since nothing queries `EmailJob`
  through another model's relation, but worth remembering if that changes later.