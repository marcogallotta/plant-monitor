# Internals

Notes for contributors. Covers non-obvious design decisions, test isolation mechanics, and conventions to follow when extending the project.

---

## Repository layout

```
backend/    # FastAPI app, Alembic migrations, static dashboard, tests
pi/         # camera capture, upload, and cleanup scripts
data/       # image files on disk (gitignored)
docs/       # design docs and this file
```

`backend/app/` holds the FastAPI app and ORM models. `backend/alembic/` holds migrations. `backend/static/` is the no-build-step dashboard (HTML + ES modules). `backend/tests/` has all backend tests.

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

### Manual upload

`POST /manual-photos` accepts a multipart upload from the dashboard. Only `image` (JPEG) is required; `captured_at`, `photo_type`, `location_id`, `growing_unit_ids`, and `note_text` are optional form fields. The filename is a random UUID hex — no timestamp stem requirement. `source` is always set to `"manual"` and `original_filename` records the browser filename. If `note_text` is supplied a `PhotoNote` with `x=0, y=0` is created in the same transaction.

### Photo classification

`PUT /photos/{photo_id}` updates `photo_type`, `location_id`, `rotation`, and/or `growing_unit_ids`. Growing unit assignments are replaced wholesale: the endpoint deletes all existing `PhotoGrowingUnit` rows for the photo then inserts the new set. Only fields present in the request body are touched (Pydantic `model_fields_set`).

### Locations and growing units

Standard CRUD via `/locations` and `/growing-units`. Both support `GET` (list), `POST` (create), `GET /{id}`, and `PUT /{id}`. `GrowingUnit` has rich optional fields (`species`, `variety`, `source`, `started_at`, `notes`, `current_location_id`) that are all nullable.

### Events

`POST /events` creates a garden event. `event_type` must be one of the values in `CARE_ACTION_TYPES` (`fed_liquid`, `fed_worm_castings`, `watered`, `harvested`, `potted_up`, `other`) — the backend enforces this with a 422 on unknown values. Optional associations: `location_id`, `growing_unit_ids` (many-to-many via `event_growing_units`), `photo_ids` (many-to-many via `event_photos`). `event_at` defaults to `now()` if omitted. `GET /events` returns all events ordered by `event_at` descending.

### Labels

`GET /labels` returns all labels ordered by usage count descending, then by name — so frequently-used labels float to the top. Labels are seeded by migration `0006_labels.py` with six common values (`watered`, `fed_liquid`, `fed_worm_castings`, `harvested`, `potted_up`, `other`). `label.name` has a unique constraint.

`POST /labels` creates a new label. The name is normalised to lowercase snake_case (whitespace → `_`). If a label with the normalised name already exists the endpoint returns it with 200 (idempotent). Returns the created label with 201.

`POST /photos/{photo_id}/labels/{label_id}` assigns a label to a photo (idempotent — duplicate assignment is a no-op). Returns the updated `PhotoOut`.

`DELETE /photos/{photo_id}/labels/{label_id}` removes an assignment; returns 404 if not currently assigned.

`GET /photos` includes `labels: [{id, name}]` on every photo via a join in `_photo_out()`. The frontend loads all labels once at boot via `GET /labels` (stored in `state.allLabels`) and renders them as chip buttons in the modal. Clicking a chip calls `toggleLabel(labelId)` which POSTs or DELETEs the assignment and updates local state without a full photo reload.

### Assistant API

`/assistant/*` is a read-only sub-router protected by a Bearer token from the `ASSISTANT_API_TOKEN` env var. It exposes `GET /assistant/summary`, `/assistant/photos`, `/assistant/photos/{id}`, `/assistant/photos/{id}/context`, `/assistant/photos/{id}/thumbnail`, `/assistant/growing-units`, `/assistant/growing-units/{id}/context`, `/assistant/locations`, `/assistant/events`, and `/assistant/unclassified`. The thumbnail endpoint resizes to 256×256 via Pillow and returns JPEG bytes. A simple in-process rate limiter allows 60 requests per 60-second window per token.

### Sensor proxy

`app/sensors.py` contains a `SensorState` class that reads through to an external sensor API (the `esp32-home-display` server). Configuration comes from three env vars:

| Var | Example |
|-----|---------|
| `SENSOR_API_URL` | `https://laptop.local:8000` |
| `SENSOR_API_KEY` | `happydevilelephantsmoking` |
| `SENSOR_SENSORS` | `[{"mac":"D5:3A:42:86:2C:63","name":"South"},…]` |

If `SENSOR_API_URL` is not set (or `SENSOR_SENSORS` is invalid JSON), `get_state()` returns `None` and all sensor endpoints return `{"available": false, "sensors": []}` — the dashboard degrades gracefully with no errors.

`SensorState` resolves MACs → sensor UUIDs lazily via `GET /sensors` on the upstream API and caches the result. It uses `verify=False` for TLS (self-signed cert on LAN).

Two proxy endpoints:

- `GET /sensors/latest` — latest temp/humidity/staleness for each configured sensor.
- `GET /sensors/photos/{photo_id}` — readings ±60 min around `photo.captured_at`, one entry per configured sensor.

The dashboard renders a compact sensor strip (top of page, auto-loaded at boot) and sensor context in the photo modal (loaded per-photo). Both are implemented in `static/sensors.js`.

---

## Session and connection lifecycle

`database.py` holds a module-level `_session_factory` that is initialised lazily on first request. This avoids connecting to Postgres at import time, which matters for tests and scripts that may set `DATABASE_URL` after the module is loaded.

FastAPI wires `get_db()` as a dependency. Tests override it with `app.dependency_overrides[get_db]` to inject a fixture-managed session (see below).

---

## Test isolation

Run all test suites with:

```sh
make test   # runs test-backend + test-pi + test-js
```

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

### JavaScript tests

`backend/tests/js/` holds Vitest tests for the pure-logic dashboard modules. Run with:

```sh
make test-js   # cd backend && npm test (vitest run)
```

Tests use `jsdom` for DOM-dependent modules. Modules that depend on `window.exifr` (e.g. `sdImport`) must stub it in the test environment. Coverage is provided by `@vitest/coverage-v8`.

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

`static/index.html` — no build step, no npm, no bundler. FastAPI serves the static directory from `_STATIC_DIR`. `app.js` is the ES module entry point; it imports from focused sibling modules and assigns the functions that HTML `onclick=` attributes need onto `window`.

Key JS state (all fields live on the single `state` object in `state.js`):

| Variable | Purpose |
|----------|---------|
| `allPhotos` | Array of photo objects from the last `GET /photos` call |
| `photoA`, `photoB` | Selected photos for comparison / flicker |
| `allLocations`, `allUnits` | Cached dropdown data from `GET /locations` and `GET /growing-units` |
| `currentIndex` | Index into `allPhotos` for the open modal photo |
| `currentPhotoId` | DB id of the currently open modal photo, used for notes API calls |
| `currentRotation` | Visual rotation (0/90/180/270) of the modal photo |
| `currentNotes` | Notes loaded for the current modal photo |
| `pendingNote` | `{x, y, x2, y2}` for a new note (x2/y2 non-null for a region); `{noteId, x, y, x2, y2}` for an edit |
| `zoom`, `panX`, `panY` | Current zoom level and pan offset in the modal viewport |
| `isPanning`, `panStart`, `wasDrag`, `isDrawingRect`, `rectStart` | Transient pointer-event state in the modal |
| `flickerShowing`, `flickerTimer` | Which slot (a/b) is visible and the auto-flicker interval id |
| `tlIndex`, `tlTimer` | Current frame index and play interval id for the timelapse panel |

Note pin positions use `left: x*100%; top: y*100%` inside `.note-pins`, which is absolutely positioned over the image wrapper. The image wrapper is `display: inline-block` so it shrinks to fit the rendered image size, not the surrounding flex container. Normalised x/y are calculated from `img.getBoundingClientRect()` at click time. For region notes (shift+drag), x2/y2 are stored the same way; rendering uses the min/max of the two corners so drag direction doesn't matter.

`zoom.js` owns all pointer events on `#zoom-viewport`. `visualToStored(rx, ry)` maps a click position in the rotated visual space back to the canonical stored coordinate system — any code that records a note position must go through this function.

### SD card import

The SD import panel lets users bulk-import photos directly from a camera SD card via the File System Access API's folder picker.

`sdImportCore.js` contains all pure logic (no DOM) and is fully unit-tested:

- `isImportablePhoto` / `isRawPhoto` — filter `.jpg`, `.jpeg`, `.orf`, `.arw`.
- `sortCameraFiles` — sorts by filename descending (matches camera sequential numbering, newest first).
- `detectSessionBoundary` — scans `lastModified` timestamps for a gap > `SD_TIME_GAP` (1 hour); returns the index of the first file in the older batch, or `-1` if no boundary found. Used to auto-select only the latest shooting session.
- `scanForJpeg` — scans a `Uint8Array` for the largest embedded JPEG (`FFD8FF … FFD9`). Used to extract preview JPEGs from RAW files.
- `deriveTimestamp` — reads `DateTimeOriginal`/`CreateDate` from EXIF (via `exifr`). Returns `{iso, badge}` where `badge` is `'ok'` (UTC offset present), `'assumed'` (no offset, browser timezone used), or `'fallback'` (no usable EXIF, `file.lastModified` used).
- `buildUploadFormData` — builds the `FormData` for `POST /manual-photos`.

`sdImport.js` owns the DOM and upload flow:

- `handleSdFolderInput` — processes the folder picker result: filters already-uploaded filenames (matched against `state.allPhotos[].original_filename`), calls `detectSessionBoundary` to auto-select the latest batch, and renders thumbnails in pages of 20.
- RAW files (`.orf`, `.arw`): thumbnails are extracted asynchronously via `extractEmbeddedJpeg`. For non-ORF RAW files a 768 KB slice is tried first; if the embedded JPEG is truncated the full file is read. The extracted JPEG blob is uploaded in place of the original file, but `original_filename` on the backend is set to the raw filename (e.g. `DSC01349.ARW`).
- EXIF timestamps are parsed asynchronously via `window.exifr` (loaded from CDN). ORF files are not supported by exifr and fall back to `lastModified`.
- `sdUploadSelected` — uploads selected photos sequentially, showing per-thumb status overlays (`…` / `✓` / `✗`).

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
