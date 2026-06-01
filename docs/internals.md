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

### Note rectangle clearing

`PUT /notes/{note_id}` uses `model_fields_set` to apply updates, so sending `x2: null, y2: null` explicitly clears an existing rectangle. Fields omitted from the request body are left unchanged. The `x2_y2_must_be_paired` validator on `NoteUpdate` catches the case where the request body itself provides only one as non-null. The endpoint additionally checks the resulting note state after applying updates — so sending `x2: null` alone against a note that already has both set is also rejected, even though the request body has both as null (one explicit, one defaulted).

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

### Exporting photos as a zip

`GET /photos/export?ids=1,2,3` streams a single `photos.zip` of the requested photos. `ids` is a comma-separated list — each part must be numeric (422 otherwise), and an empty list is rejected. Photos whose `storage_path` resolves outside `PHOTOS_DIR` are skipped (path-traversal guard via `Path.relative_to`), as are missing files and undecodable images.

Rotation is **baked in**: if `photo.rotation` is non-zero the image is re-encoded through Pillow (`_ROTATION_TRANSPOSE` maps stored rotation → `Image.Transpose`) and saved as JPEG at quality 90; otherwise the original file is written verbatim.

The route is registered **before** `GET /photos/{filename}` so FastAPI does not match `export` as a filename. Keep it above that handler if you reorder routes.

### Manual upload

`POST /manual-photos` accepts a multipart upload from the dashboard. Only `image` (JPEG) is required; `captured_at`, `photo_type`, `location_id`, `growing_unit_ids`, `note_text`, `rotation`, `original_size_bytes`, and `source` are optional form fields. The filename is a random UUID hex — no timestamp stem requirement. `source` defaults to `"manual"` when not supplied; pass `"phone"` for phone uploads. `original_filename` records the browser filename. If `note_text` is supplied a `PhotoNote` with `x=0, y=0` is created in the same transaction.

### Photo source field

`Photo.source` tracks where a photo originated. Known values:

| Value | Set by |
|-------|--------|
| `pi` | Pi camera upload (`POST /photos`) |
| `manual` | Dashboard manual upload (`POST /manual-photos` default) |
| `phone` | Phone browser upload (same endpoint, `source=phone`) |
| `sd` | SD/camera card backend import (`POST /camera-import/import`) |

`GET /photos` accepts a `source` query parameter to filter by source. The gallery filter bar exposes this as a dropdown.

### Rotation validation

`rotation` must be one of `0`, `90`, `180`, `270` in all write paths. It is enforced by a `field_validator` on `PhotoClassify` (PUT /photos/{id}), an inline check in the manual upload endpoint, and a `field_validator` on `ImportRequest.rotations` for SD import. `save_photo()` raises `ValueError` as a final guard before any file I/O — invalid rotation never reaches disk.

### Photo classification

`PUT /photos/{photo_id}` updates `photo_type`, `location_id`, `rotation`, and/or `growing_unit_ids`. Growing unit assignments are replaced wholesale: the endpoint deletes all existing `PhotoGrowingUnit` rows for the photo then inserts the new set. Only fields present in the request body are touched (Pydantic `model_fields_set`).

### Batch classification

`POST /photos/batch` applies the same edits to many photos in one transaction. Body: `ids` (required, non-empty), `photo_type`, `location_id`, `add_unit_ids`, `add_label_ids`. `photo_type`/`location_id` follow the same `model_fields_set` rule as `PUT /photos/{id}` — present-in-body sets the value (including explicit `null` to clear), omitted leaves it untouched. `add_unit_ids`/`add_label_ids` are **additive merges**: they never remove existing assignments and skip ids already present. Unknown photo/location/unit/label ids return 404. Existing assignments are preloaded in one query per table and the in-memory cache is updated as inserts are queued, so duplicate ids in a single request (`add_unit_ids: [7, 7]`) can't produce a composite-PK collision. Returns the updated `PhotoOut` rows.

The gallery select bar drives this: the `Set type` / `Set location` / `+ Unit` / `+ Label` dropdowns each fire one batch call on change, splice the returned rows into `state.allPhotos` **without re-rendering the grid** (so the selection survives across chained actions), then reset to their placeholder.

### Photo deletion

`DELETE /photos/{photo_id}` removes a photo and all dependent rows (notes, labels, growing unit assignments, event associations) in a single transaction, then attempts to delete the image and metadata files from disk. File deletion is best-effort — an `OSError` is logged but does not fail the request (the DB row is already gone). Returns 204 on success.

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
make test        # runs test-backend + test-pi + test-js
make test-e2e    # Playwright end-to-end tests — NOT included in make test; must be run separately
```

**Always run both.** `make test` does not include `make test-e2e`. Any change to the dashboard, API, or photo flow should be followed by both commands.

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

After each test, truncates all data tables with `RESTART IDENTITY CASCADE`, then re-inserts the seven seed labels from migration `0007` (`aphids`, `yellowing`, `mildew`, `damage`, `new_growth`, `recovery`, `watch`). This keeps tests independent regardless of commit behaviour inside them and ensures the `labels` table is always in a known state — custom labels created by one test do not leak into the next.

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

`static/index.html` — no build step, no npm, no bundler. FastAPI serves the static directory from `_STATIC_DIR`. `app.js` is the ES module entry point; it imports from focused sibling modules and assigns the functions that HTML `onclick=` attributes need onto `window`. Any new function called from an `onclick=` attribute in `index.html` must be added to both the import and the `Object.assign(window, …)` call at the bottom of `app.js`, or it will throw `ReferenceError: X is not defined` at runtime.

### Tab navigation

`switchTab(name)` in `app.js` activates a tab panel (`#tab-{name}`) and its button, then writes `tab={name}` into the URL hash. On page load, the active tab is read from the hash (falling back to `localStorage.activeTab`, then `gallery`). This means the URL is always shareable with the correct tab open.

### URL hash filter state

All gallery filter state is serialised into the URL hash by `writeFiltersToHash()` in `photos.js`. Keys stored: `tab`, `start`, `end`, `source`, `ptype`, `location`, `unit`, `label`. `readFiltersFromHash()` is called on boot to restore all filters before the first `loadPhotos()` call. Tab changes call `history.replaceState` to merge `tab` into the existing hash without disturbing other keys.

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

### Quick-filter chips

`renderQuickChips()` in `photos.js` renders a row of `<button class="qchip">` elements above the gallery grid — one per growing unit, then a separator, then one per label. Clicking a chip toggles `activeUnitId` / `activeLabelId` in module scope, writes both to the URL hash, and calls `loadPhotos()`. Only one unit and one label can be active at a time; clicking the active chip clears it. Chip state is restored from the URL hash at module load before `renderQuickChips()` is first called.

### Gallery delete

`gridDelete(e, photoId)` in `photos.js` shows a `confirm()` dialog then calls `DELETE /photos/{photo_id}`. On success it removes the photo from `state.allPhotos` and re-renders the grid without a full reload.

### Gallery select mode

`photos.js` holds two module-level pieces of state: `selectMode` (bool) and `selectedIds` (a `Set`). `toggleSelectMode()` flips the mode, clears the selection, and toggles the `select-mode` class on the grid plus the visibility of the `#select-bar`. Rendering checks `selectedIds.has(p.id)` to apply the `selected` class, so a grid re-render preserves the selection.

Selection inputs:

- **Click** — the grid's click handler toggles a single card's membership (guarded by `if (!selectMode) return`).
- **`selectAll()`** — adds every photo in `state.allPhotos` to the set.
- **Drag-to-select** — `mousedown` on a card starts a drag (`_dragSelecting`), records the toggle direction from the first card (`_dragToggleTo = !selectedIds.has(id)`), and applies it; `mouseover` while dragging applies the same direction to each hovered card; `mouseup` ends the drag. The `mousedown` handler calls `e.preventDefault()` to stop the browser's native image-drag from swallowing `mouseover` events, and sets `_dragMoved = true` immediately so the click event that follows `mousedown` is suppressed (otherwise the first card would be double-toggled — click would undo the mousedown toggle).

Selection actions (operate on `selectedIds`):

- **`downloadSelected()`** — creates an `<a download>` pointing at `/photos/export?ids=…` and clicks it (single zip download).
- **`copySheet()`** — builds a contact-sheet PNG on a `<canvas>` and writes it to the clipboard via `ClipboardItem`. Layout: up to 2 columns, `TARGET_W` 2048px, per-cell size `max(512, TARGET_W/cols - pad)` so a single photo is never tiny, 22px bold labels showing growing unit + capture date. Images are fetched via `orientedUrl(photo)` (server-rotated). If `navigator.clipboard.write()` is denied (e.g. Brave shields, lost focus) it falls back to opening the PNG blob in a new tab. The build runs inside the user-gesture window so the clipboard write is permitted.
- **`deleteSelected()`** — `confirm()`s, then issues `DELETE /photos/{id}` per selected id and updates state.

Note pin positions use `left: x*100%; top: y*100%` inside `.note-pins`, which is absolutely positioned over the image wrapper. The image wrapper is `display: inline-block` so it shrinks to fit the rendered image size, not the surrounding flex container. Normalised x/y are calculated from `img.getBoundingClientRect()` at click time. For region notes (shift+drag), x2/y2 are stored the same way; rendering uses the min/max of the two corners so drag direction doesn't matter.

`zoom.js` owns all pointer events on `#zoom-viewport`. `visualToStored(rx, ry)` maps a click position in the rotated visual space back to the canonical stored coordinate system — any code that records a note position must go through this function.

### SD card import

The SD import panel supports two modes: a backend scanner (primary) and a browser folder-picker (fallback).

**Backend scanner** (`GET /camera-import/scan`, `POST /camera-import/import`):

- Configured via `IMPORT_SCAN_PATH` env var (e.g. `/media/marco/4621-0000/DCIM/101MSDCF`). The host's `/media` directory is mounted into the container at `/media` with `propagation: rslave` (see `docker-compose.yml`), so paths are identical inside and outside the container and SD cards mounted on the host after the container starts appear inside it.
- `rslave` propagation only works if `/media` is its own **shared mountpoint** on the host. On a default install `/media` is just a directory on the root partition, so card mounts never propagate in. `scripts/media-shared.service` is a oneshot systemd unit that bind-mounts `/media` onto itself and marks it shared before `docker.service` starts. Install with `sudo cp scripts/media-shared.service /etc/systemd/system/ && sudo systemctl enable --now media-shared.service`.
- `app/camera_import.py` owns scanning, HMAC-based opaque file IDs, in-process scan cache (TTL: `IMPORT_SCAN_CACHE_TTL_SECONDS`), embedded JPEG extraction from RAW files, and import logic.
- Duplicate detection uses `original_filename + original_size_bytes` (source file size) — tolerates camera counter rollover where `DSC00001.ARW` repeats on a new card.
- `save_photo()` in `camera_import.py` is the shared helper used by both `/camera-import/import` (source `"sd"`) and `/manual-photos` (source `"manual"`). It writes files atomically (tmp → rename) and commits the DB row.
- Clicking **Scan camera/card** calls `scanCameraImport()` in `api.js`, builds the thumbnail grid, and auto-selects the latest shooting session via `detectSessionBoundary()` on `mtime_ms`.
- Clicking **Import selected** calls `importCameraPhotos()` with the selected opaque file IDs; per-thumb overlays show created / skipped / failed.

**Phone upload** (`Choose photos` button, mobile only):

Same code path as the browser folder-picker but `sdMode` is set to `'phone'`. The only behavioural difference is that `buildUploadFormData` receives `src = 'phone'` so uploaded photos get `source = "phone"` on the backend.

**Browser folder-picker** (fallback, `Choose folder` button):

`sdImportCore.js` contains all pure logic (no DOM) and is fully unit-tested:

- `isImportablePhoto` / `isRawPhoto` — filter `.jpg`, `.jpeg`, `.orf`, `.arw`.
- `sortCameraFiles` — sorts by filename descending (matches camera sequential numbering, newest first).
- `detectSessionBoundary` — scans `lastModified` timestamps for a gap > `SD_TIME_GAP` (1 hour); returns the index of the first file in the older batch, or `-1` if no boundary found.
- `scanForJpeg` — scans a `Uint8Array` for the largest embedded JPEG (`FFD8FF … FFD9`). Used to extract preview JPEGs from RAW files.
- `deriveTimestamp` — reads `DateTimeOriginal`/`CreateDate` from EXIF (via `exifr`). Returns `{iso, badge}` where `badge` is `'ok'` (UTC offset present), `'assumed'` (no offset, browser timezone used), or `'fallback'` (no usable EXIF, `file.lastModified` used).
- `buildUploadFormData` — builds the `FormData` for `POST /manual-photos`.

`sdImport.js` owns the DOM and both upload flows. `sdMode` tracks which mode is active (`'browser'` or `'backend'`). `sdUploadSelected` branches on `sdMode` to call either `sdUploadBrowser` (sequential per-file via `/manual-photos`) or `sdUploadBackend` (batch via `/camera-import/import`).

---

## Seed script

`scripts/seed.py` downloads three Picsum placeholder images and uploads each through `POST /photos`. It does not write directly to `data/photos/`. The script accepts a `--backend-url` flag (defaults to `http://localhost:8000`) and an injectable `client` parameter for unit testing without a live server.

Run via Make:

```sh
make seed   # runs inside Docker, hits http://backend:8000
```

### Timestamp repair script

`scripts/fix_timestamps.py` (and the container-path copy at `backend/scripts/fix_timestamps.py`) scans every photo, reads EXIF `DateTimeOriginal`, and corrects `captured_at` where it differs. It is a dry run by default; pass `--apply` to write changes.

Photos whose EXIF carries **no UTC offset** are refused, not guessed — assuming a wall-clock time is UTC would corrupt timestamps for any photo actually taken in another timezone. Those are reported separately in the summary as "no tz offset" so they can be handled by hand.

---

## Pi camera node

`pi/camera.py` mocks the Raspberry Pi hardware (`picamera2`) until the device is available. The mock returns stub image bytes (`b"FAKEJPEG"`) so the upload and cleanup scripts can be tested without physical hardware.

Upload attempts are retried if the backend is unreachable. Photos are cleaned up locally after 7 days.

`run_upload()` checks the archive destination **before** reading bytes or POSTing. If both destination files already exist the source pair is deleted immediately (the archive is complete; no POST needed). If only one destination file exists the pair is left untouched — that is a partial-archive state that requires manual investigation. This pre-check prevents an infinite retry loop that would otherwise occur when a POST succeeds but the archive move is skipped due to a destination collision.

---

## Adding a new stage

1. Add the sub-stage to `docs/design-stage2.md` (or the relevant design doc).
2. Write failing tests first.
3. Write the migration if schema changes are needed (`alembic revision -m "…"`).
4. Implement the feature.
5. Run `make test-backend` — all tests including the new ones must pass.
