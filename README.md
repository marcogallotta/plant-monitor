# plant-monitoring

A small plant-tracking system for a balcony setup. A Raspberry Pi camera node takes scheduled photos and uploads them to a laptop backend. The backend stores photos and metadata in Postgres and serves a dashboard for review, comparison, timelapse playback, notes, and SD card import.

## Architecture

```
Raspberry Pi Zero 2W + Camera
        |
        | HTTP upload (photo + metadata JSON)
        v
FastAPI backend + Postgres (laptop)
        |
        +--> data/photos/   (image files on disk)
        +--> Postgres        (photo records, notes, labels, locations, growing units, events)
        +--> /              (dashboard)
```

## Requirements

- Docker and Docker Compose

## Running locally

```sh
make up
```

Backend is available at `http://localhost:8001` (override via `BACKEND_PORT` in `.env`).

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
make test           # all three
```

## Project structure

```
backend/
  app/
    main.py             # FastAPI app, routes
    models.py           # SQLAlchemy ORM models
    database.py         # engine, session factory, get_db dependency
    camera_import.py    # SD card scan and import logic
    sensors.py          # proxy to external sensor API (esp32-home-display)
  alembic/              # database migrations
  scripts/seed.py       # dev seed script (downloads Picsum images, uploads via API)
  static/
    index.html          # dashboard (no build step)
    app.js              # ES module entry point
    *.js                # focused sibling modules (zoom, sdImport, sensors, …)
  tests/
    *.py                # backend pytest tests
    js/                 # Vitest tests for pure-logic dashboard modules

pi/
  camera.py             # photo capture (mocks picamera2 until Pi is available)
  upload.py             # upload to backend with retry
  cleanup.py            # prune old local photos after 7 days

data/photos/            # stored image files (gitignored)
docs/                   # design documents and roadmap
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
- A/B comparison: select two photos and view side by side
- Flicker comparison: toggle or auto-flicker between A and B to spot changes
- Timelapse: play/pause, prev/next, speed control
- Notes: click to pin a point note; shift+drag for a region note; edit and delete
- Labels: chip buttons in the modal for quick tagging
- Classify: set photo type, location, rotation, and growing unit assignments
- Manual upload: drag-and-drop or file-picker for photos taken outside the Pi
- SD card import: backend scanner (primary) or browser folder-picker (fallback); auto-detects current shooting session by timestamp gap
- Phone upload: mobile browser file picker (shown automatically on touch devices); uploaded photos tagged with `source=phone`
- Sensor strip: live temp/humidity at the top of the page; per-photo sensor context in the modal

## Roadmap

See `docs/roadmap.md`. Planned stages after the current dashboard foundation:

1. ~~Photo capture, upload, storage~~ (done)
2. ~~Dashboard: timeline, comparison, timelapse, notes~~ (done)
3. Simple image metrics (green area, canopy coverage, blur detection)
4. Decision support rules
5. ML / computer vision experiments
