# plant-monitoring

A plant-tracking system for an edible-plant growing setup. A Raspberry Pi camera node takes
scheduled photos and uploads them to a laptop backend. The backend stores photos and metadata in
Postgres and serves a dashboard for review, comparison, timelapse playback, notes, labels,
AI-assisted tagging, and photo/SD-card import.

The project is now oriented around two tracks: **sparse, calibrated irrigation** and **AI-assisted
photo-to-plant tagging** (the camera as context for watering decisions). See
[`docs/roadmap.md`](docs/roadmap.md) for the current direction and
[`docs/internals.md`](docs/internals.md) for the engineering details.

## Architecture

```text
Raspberry Pi Zero 2W + Camera + Flower Care sensor
        |
        | HTTP upload (photo + metadata JSON)
        | POST /sensors/ingest  (Flower Care history via BLE, hourly)
        v
FastAPI backend + Postgres (laptop)
        |
        +--> data/photos/    (image files + thumbnail cache on disk)
        +--> Postgres         (photos, notes, labels, locations, growing units, events,
        |                      AI tag suggestions, sensor_readings)
        +--> /               (password-protected dashboard)
        +--> /assistant/*    (token-protected read-only API, e.g. for a ChatGPT action)
        +--> /sensors/latest              (SwitchBot microclimate proxy)
        +--> /sensors/flower-care/latest  (Flower Care — one row per sensor)
        +--> /sensors/flower-care/{mac}/readings  (time-windowed history)
```

A separate offline worker (`scripts/compute_stabilization.py`, run on a systemd timer) computes
per-photo tilt/drift transforms so timelapse and comparison stay aligned.

## Requirements

- Docker and Docker Compose

## Running locally

The dev stack is managed by a systemd user service. One-time setup:

```sh
make install
loginctl enable-linger $USER   # start at boot, survive logout
```

After that, use Make as normal:

```sh
make up    # systemctl --user start plant-monitoring
make down  # systemctl --user stop plant-monitoring
```

Backend is available at `http://localhost:8001` (override via `BACKEND_PORT` in `.env`).

### Authentication and public access

Auth is **off by default** (dev/tests). Setting `DASHBOARD_PASSWORD` (plus `SESSION_SECRET`) turns
on session-cookie login for the dashboard; the Pi ingest endpoint and the read-only `/assistant` API
use their own bearer tokens (`INGEST_API_TOKEN`, `ASSISTANT_API_TOKEN`). `make tunnel` exposes the
backend over a Tailscale Funnel. See the "Auth and access" section of
[`docs/internals.md`](docs/internals.md) for details.

Run database migrations:

```sh
make migrate
```

Seed placeholder photos for development:

```sh
make seed
```

## Running tests

```sh
make test-backend   # backend (runs in isolated Docker Compose stack)
make test-pi        # Pi camera scripts
make test-js        # JavaScript dashboard modules (Vitest)
make test           # all three of the above

make e2e-install    # one-time: install Playwright + Chromium
make test-e2e       # Playwright end-to-end tests (NOT included in `make test`)
```

## Project structure

```text
backend/
  app/
    main.py             # FastAPI app, photo routes, auth middleware, health checks
    routers/            # assistant.py, sensors.py, suggestions.py (mounted sub-APIs)
    models.py           # SQLAlchemy ORM models
    schemas.py          # Pydantic request/response models
    helpers.py          # shared query + response serializers (_photo_out, …)
    database.py         # engine, session factory, get_db dependency
    camera_import.py    # SD card scan and import logic
    exif.py             # EXIF capture-time parsing (shared by upload + repair)
    sensors.py          # client for an external temp/humidity sensor API
  alembic/              # database migrations
  static/
    index.html          # dashboard (no build step), login.html
    app.js              # ES module entry point
    *.js                # focused sibling modules (zoom, sdImport, sensors, review, …)
  tests/
    *.py                # backend pytest tests
    js/                 # Vitest tests for pure-logic dashboard modules

pi/
  camera.py             # photo capture (mocks picamera2 until Pi is available)
  upload.py             # upload to backend with retry
  cleanup.py            # prune old local photos after 7 days
  xiaomi_ingest.py      # Flower Care BLE history read + ingest to backend (hourly timer)

scripts/                # maintenance (seed.py, fix_timestamps.py), the stabilization
                        # worker, the AI-tagging pipeline, and irrigation research
e2e/                    # Playwright end-to-end tests
data/                   # image files + thumbnail cache (gitignored)
docs/                   # design docs, internals, and the roadmap
```

## Dashboard features

- Photo timeline with time-range, source, type, location, growing unit, and label filters
- Quick-filter chips for growing units and labels above the gallery grid
- Filter and tab state persisted in the URL hash (shareable links)
- Click a photo to open it in a modal; arrow keys to navigate
- Delete a photo from the gallery (removes DB record and files on disk)
- Select mode: toggle on to multi-select photos by click, select-all, or drag across cards
  - Download selected as a single `photos.zip` (rotation baked in)
  - Copy a contact sheet of the selection to the clipboard (paste into ChatGPT or anywhere)
  - Bulk-delete the selection
- A/B comparison: select two photos and view side by side (tilt/drift-stabilized)
- Flicker comparison: toggle or auto-flicker between A and B to spot changes
- Timelapse: play/pause, prev/next, speed control (frames stabilized to a reference)
- Notes: click to pin a point note; shift+drag for a region note; edit and delete
- Labels: chip buttons in the modal for quick tagging
- Classify: set photo type, location, rotation, and growing unit assignments
- Manual upload: drag-and-drop or file-picker for photos taken outside the Pi
- SD card import: backend scanner (primary) or browser folder-picker (fallback); auto-detects
  current shooting session by timestamp gap
- Phone upload: mobile browser file picker (shown automatically on touch devices); uploaded photos
  tagged with `source=phone`
- Sensor strip: live temp/humidity at the top of the page; per-photo sensor context in the modal
- Review tab: keyboard-driven queue (accept / reject / delete) for AI-suggested plant tags, photo
  type, and labels, fed by the vision-tagging pipeline
- Login: optional password-protected access when `DASHBOARD_PASSWORD` is set

## Roadmap

[`docs/roadmap.md`](docs/roadmap.md) is the navigational entry point. The photo capture, storage,
and dashboard foundation is in place; current work is organized into tracks:

- **A — Irrigation control** ([`docs/irrigation.md`](docs/irrigation.md)): the primary product — a
  sparse, calibrated water-balance model with pump dosing and safety limits.
- **B — Photo-to-unit tagging** ([`docs/vision-tagging.md`](docs/vision-tagging.md)): AI-assisted
  tagging of Pi/phone/camera photos to growing units, reviewed in the Review tab.
- **C — Nursery direction** ([`docs/nursery.md`](docs/nursery.md)): crop priorities and scaling
  strategy.
- **D — Platform / import / review UX**: import, sync, stable IDs, and data integrity (this repo).
