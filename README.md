# Backend Assessment — Django

Django project covering 4 sections: diagnosing and fixing an N+1 query bug, a rate-limited
Celery job queue, multi-tenant ORM isolation, and a written architecture review. Written answers
are in [ANSWERS.md](ANSWERS.md), job queue design in [DESIGN.md](DESIGN.md).

## Demo Recording

Live run of the queue, rate limiter, retry/backoff, and worker crash recovery:
https://www.loom.com/share/141fb2dfca234e8188b82fa4ec244eed

## Requirements

- Python 3.12 (see `.python-version`)
- Redis (for Celery broker — see [Redis setup](#environment-variables) below)

## Setup

Pick one: `uv` (recommended, this project was built with it) or plain `pip`.

### Option A — uv

```bash
uv sync
```

This creates `.venv` and installs everything pinned in `uv.lock`.

### Option B — pip

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Environment variables

Create a `.env` file at the repo root (or export these in your shell):

```
REDIS_URL=redis://localhost:6379/0
```

`REDIS_URL` is required — it's the Celery broker. Don't hardcode credentials in `settings.py`;
if you're testing against a hosted Redis (Upstash, etc.), use its connection string here instead.

## Database setup

SQLite, no separate DB server needed.

```bash
# uv
uv run python manage.py migrate

# pip (venv activated)
python manage.py migrate
```

## Seed data

Needed for Section 1 (N+1 demo). Seeds 10 customers with 50-200 orders each, 2-4 items per order.

```bash
uv run python manage.py seed_customer
# or, with pip:
python manage.py seed_customer
```

## Running the app

**Web server:**

```bash
uv run python manage.py runserver
# or: python manage.py runserver
```

Visit:
- `http://127.0.0.1:8000/admin/` — Django admin (Unfold theme). Create a superuser first:
  `python manage.py createsuperuser`.
- `http://127.0.0.1:8000/silk/` — django-silk query profiler.
- `http://127.0.0.1:8000/api/orders/summary/` — Section 1 endpoint (filterable order summary).
- `http://127.0.0.1:8000/api/orders/customers/<id>/summary/` — N+1 demo endpoint. Add
  `?fixed=1` to use the `select_related`/`prefetch_related` version. See
  [ANSWERS.md](ANSWERS.md) for before/after query counts.

**Celery worker** (needed for Section 2, job queue — run in a separate terminal, Redis must be
reachable via `REDIS_URL`):

```bash
uv run celery -A core worker -l info
# or: celery -A core worker -l info
```

On Windows, Celery's default prefork pool doesn't work — add `-P solo` or `-P gevent`:

```bash
celery -A core worker -l info -P solo
```

## Running tests

```bash
uv run python manage.py test
# or: python manage.py test

# a single app
python manage.py test tenants
python manage.py test notifications
```

## Project layout

```
core/               settings, root urls, celery app
orders/             Section 1 — order summary endpoint, N+1 demo + fix
notifications/      Section 2 — Celery-backed email job queue, rate limiting, dead-letter handling
tenants/            Section 3 — tenant-scoped ORM manager, middleware, isolation tests
ANSWERS.md          written answers — Section 1 diagnosis + Section 4 architecture review (A/B/C)
DESIGN.md           architecture notes for the job queue (Section 2)
assests/            profiler screenshots referenced from ANSWERS.md
```