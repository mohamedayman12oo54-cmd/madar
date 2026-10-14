# Running Madar on PostgreSQL

PostgreSQL is the **only** supported database; SQLite support was removed.

The application is database-agnostic Django ORM code — there is **no raw SQL,
no SQLite-specific query, and no naive datetime arithmetic** anywhere in the
backend (verified by scan). Switching engines is therefore configuration plus
the driver.

## 1. Install the driver

    pip install -r requirements.txt     # includes psycopg[binary]

## 2. Configure through environment variables only

Never hardcode credentials. In `.env`:

    DB_NAME=madar
    DB_USER=madar
    DB_PASSWORD=<secret>
    DB_HOST=localhost
    DB_PORT=5432
    DB_CONN_MAX_AGE=60          # reuse connections (each PG connection forks a backend)
    DB_CONN_HEALTH_CHECKS=True  # drop dead pooled connections instead of erroring

## 3. Create the schema from an empty database

    createdb madar
    python manage.py migrate
    python manage.py createcachetable   # throttle counters (shared cache)

`migrate` builds the complete schema from scratch; every app's migrations are
committed and `makemigrations --check` reports no pending changes.

## 4. Verify

    python manage.py check
    python manage.py test            # runs against the configured engine

## Compatibility notes

* `JSONField` (ai.AIOperation.evidence/sources, studentarea quiz questions/
  answers, accounts.PendingAuth.payload) maps to native `jsonb` — strictly
  better supported than on SQLite.
* `CheckConstraint` / `UniqueConstraint(condition=...)` (tenant isolation,
  AI idempotency, "assistant operations never reference a student") become
  real partial indexes and table constraints on PostgreSQL; SQLite enforced
  them too, so behaviour is unchanged.
* `__iexact` / `__icontains` compile to `ILIKE` on PostgreSQL. Results are
  case-insensitive as intended; note PostgreSQL applies the database collation,
  so ordering of mixed-case/Arabic text can differ from SQLite.
* All timestamps are timezone-aware (`USE_TZ`), stored as `timestamptz`.
* Transactions: the atomic Fast-Session write + event hand-off and the AI
  worker's single-row conditional claim both rely only on standard
  `transaction.atomic()` / conditional `UPDATE`, which behave identically.

## Migrating existing data from the old SQLite file (one-time)

The new settings cannot open SQLite, so dump the data FIRST, using the previous
version of the code (before this change) that still reads `db.sqlite3`:

    # with the OLD code/settings still active (SQLite)
    python manage.py dumpdata --natural-foreign --natural-primary \
        --exclude contenttypes --exclude auth.permission --exclude sessions \
        --indent 2 -o madar-dump.json

    # switch .env to PostgreSQL, then
    python manage.py migrate
    python manage.py loaddata madar-dump.json

Excluding `contenttypes`/`auth.permission` avoids primary-key collisions with
the rows `migrate` already created. This carries users, students, teachers,
groups, sessions, attendance, recitation, evaluations, payments, content and
video metadata, AI operations, notes and notifications. Take a backup first
and verify row counts per model after loading.
