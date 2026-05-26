# Internals

Notes for contributors. Covers non-obvious design decisions, test isolation mechanics, and conventions to follow when extending the project.

---

## Repository layout

```
backend/
  app/
    main.py         # FastAPI app, all routes, request validation
    models.py       # SQLAlchemy ORM models
    database.py     # engine, session factory, get_db dependency
  alembic/
    env.py          # reads DATABASE_URL, binds Base.metadata
    versions/       # migration scripts (prefix 0001_, 0002_, …)
  scripts/
    seed.py         # dev seed: downloads Picsum images, uploads via POST /photos
  static/
    index.html      # single-file dashboard (inline CSS + JS, no build step)
  tests/
    conftest.py     # all shared fixtures
    test_schema.py  # DB schema assertions (tables, columns, constraints, indexes)
    test_upload_db.py
    test_list_serve.py
    test_notes.py
    test_seed.py
    test_dashboard.py
    test_photos.py  # original upload endpoint tests

pi/
  camera.py         # photo capture (mocks hardware until Pi arrives)
  upload.py         # uploads photos to backend
  cleanup.py        # prunes local photos older than 7 days

data/photos/        # image files on disk (gitignored)
docs/               # design docs and this file
```

---

## Database

### ORM and migrations

Models live in `app/models.py` using SQLAlchemy 2 `DeclarativeBase` / `Mapped` / `mapped_column` style.

Migrations live in `alembic/versions/`. Name files with a zero-padded numeric prefix (`0002_…`, `0003_…`). Every schema change needs a migration — never use `Base.metadata.create_all()` in production or test setup.

Running migrations:

```sh
make migrate            # applies head against the dev DB inside Docker
```

Writing a new migration:

```sh
docker compose run --rm backend alembic revision -m "describe the change"
# then fill in upgrade() and downgrade() in the generated file
```

`alembic/env.py` reads `DATABASE_URL` from the environment and imports `Base.metadata` so Alembic can do autogenerate diffs if needed.

### Transaction ownership

`_upsert_photo_record()` in `main.py` calls `db.flush()` — it stages work into the session but does **not** commit. The calling endpoint owns the commit. This keeps the helper reusable without surprising callers.

### `updated_at` on `photo_notes`

The column has a `server_default=func.now()` for insert, but there is no `onupdate` trigger. The `PUT /notes/{note_id}` endpoint sets `note.updated_at = datetime.now(timezone.utc)` explicitly before committing. If you add another code path that mutates a note, do the same.

---

## Photo upload flow

`POST /photos` accepts a multipart upload with two fields: `image` (`.jpg`) and `metadata` (`.json`).

Validation steps (all return 422 on failure):

1. Both filenames must match `YYYY-MM-DDTHHMMSSZ` (stem) with `.jpg` / `.json` extensions.
2. Both stems must be identical.
3. The metadata JSON must contain `captured_at` and `filename`.
4. `metadata.filename` must match the uploaded image filename.

File write is atomic: files are written to `.tmp` paths first, then renamed. Partial state on disk (one file but not the other) returns 409 rather than silently ignoring or overwriting.

After files are on disk, `_upsert_photo_record()` creates the DB row if one doesn't already exist for that filename. Duplicate uploads (both files already present) return `{"status": "duplicate"}` without an error.

### Serving photos

`GET /photos/{filename}` validates the filename format, checks the DB for a matching record, then serves the file from `data/photos/`. The DB check (not just a filesystem check) prevents path traversal — a filename that doesn't match any DB row gets a 404 even if the file happens to exist on disk.

---

## Session and connection lifecycle

`database.py` holds a module-level `_session_factory` that is initialised lazily on first request. This avoids connecting to Postgres at import time, which matters for tests and scripts that may set `DATABASE_URL` after the module is loaded.

FastAPI wires `get_db()` as a dependency. Tests override it with `app.dependency_overrides[get_db]` to inject a fixture-managed session (see below).

---

## Test isolation

Tests run inside Docker Compose using `docker-compose.test.yml`, which spins up a separate `db-test` service pointing at the `plantmonitoring_test` database. The test stack uses project name `plant-monitoring-test` so its network (`plant-monitoring-test_default`) is entirely separate from the dev stack's network. Running `make test-backend` cannot interfere with a running `make up`.

### conftest.py fixtures

**`engine` (session-scoped)**

Runs once per test session:

1. Asserts the URL contains `plantmonitoring_test` — hard stops if pointed at the wrong DB.
2. Calls `alembic stamp base` to reset the `alembic_version` row.
3. Calls `Base.metadata.drop_all()` to remove all tables.
4. Calls `alembic upgrade head` to re-run migrations from scratch.

This ensures every test run exercises the real migrations, not just the ORM definitions. A broken migration is caught here rather than silently passing.

No teardown step — `make test-backend` runs `down -v` after tests finish, which destroys the Docker volume entirely.

**`db_session` (function-scoped)**

Opens a plain session from the engine. No transaction wrapping — tests commit freely, which is realistic.

**`clean_tables` (autouse, function-scoped)**

After each test, truncates `photo_notes` and `photos` with `RESTART IDENTITY CASCADE`. This keeps tests independent regardless of commit behaviour inside them.

**`isolated_photos_dir` (autouse, function-scoped)**

Patches `app.main.PHOTOS_DIR` to a `tmp_path` for each test. Prevents test photos from accumulating under `data/photos/` and stops tests from seeing each other's files.

**`client` (function-scoped)**

Installs a `get_db` override so the FastAPI app uses the same session as the test. Clears overrides on teardown.

---

## Docker Compose setup

Two compose files:

| File | Purpose | DB service | Project name |
|------|---------|------------|--------------|
| `docker-compose.yml` | Dev stack | `db` → `plantmonitoring` | `plant-monitoring` |
| `docker-compose.test.yml` | Test stack | `db-test` → `plantmonitoring_test` | `plant-monitoring-test` |

The `Makefile` passes `-p plant-monitoring-test` when invoking the test compose to guarantee network isolation.

`BACKEND_PORT` defaults to `8000` in `docker-compose.yml` but the local `.env` overrides it to `8001` to avoid clashes with other projects on the same machine.

---

## Dashboard

`static/index.html` is a single file with inline CSS and JS — no build step, no npm, no bundler. FastAPI reads and serves it directly from `_STATIC_DIR`.

Key JS state:

| Variable | Purpose |
|----------|---------|
| `allPhotos` | Array of photo objects from the last `GET /photos` call |
| `photoA`, `photoB` | Selected photos for comparison / flicker |
| `currentIndex` | Index into `allPhotos` for the open modal photo |
| `currentPhotoId` | DB id of the currently open modal photo, used for notes API calls |
| `currentNotes` | Notes loaded for the current modal photo |
| `pendingNote` | `{x, y}` for a new note being composed, or `{noteId, x, y}` for an edit |

Note pin positions use `left: x*100%; top: y*100%` inside `.note-pins`, which is absolutely positioned over the image wrapper. The image wrapper is `display: inline-block` so it shrinks to fit the rendered image size, not the surrounding flex container. Normalized x/y are calculated from `img.getBoundingClientRect()` at click time.

---

## Seed script

`scripts/seed.py` downloads three Picsum placeholder images and uploads each through `POST /photos`. It does not write directly to `data/photos/`. The script accepts a `--backend-url` flag (defaults to `http://localhost:8000`) and an injectable `client` parameter for unit testing without a live server.

Run via Make:

```sh
make seed   # runs inside Docker, hits http://backend:8000
```

---

## Pi camera node

`pi/camera.py` mocks the Raspberry Pi hardware (`picamera2`) until the device is available. The mock returns stub image bytes (`b"FAKEJPEG"`) so the upload and cleanup scripts can be tested without physical hardware.

Upload attempts are retried if the backend is unreachable. Photos are cleaned up locally after 7 days.

---

## Adding a new stage

1. Add the sub-stage to `docs/design-stage2.md` (or the relevant design doc).
2. Write failing tests first.
3. Write the migration if schema changes are needed (`alembic revision -m "…"`).
4. Implement the feature.
5. Run `make test-backend` — all tests including the new ones must pass.
