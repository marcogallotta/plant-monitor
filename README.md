# plant-monitoring

A small plant-tracking system for a balcony setup. A Raspberry Pi camera node takes scheduled photos and uploads them to a laptop backend. The backend stores photos and metadata in Postgres and serves a dashboard for review, comparison, timelapse playback, and notes.

## Architecture

```
Raspberry Pi Zero 2W + Camera
        |
        | HTTP upload (photo + metadata JSON)
        v
FastAPI backend + Postgres (laptop)
        |
        +--> data/photos/   (image files on disk)
        +--> Postgres        (photo records, notes)
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
make test           # both
```

## Project structure

```
backend/
  app/
    main.py         # FastAPI app, routes
    models.py       # SQLAlchemy ORM models (Photo, PhotoNote)
    database.py     # engine, session factory, get_db dependency
  alembic/          # database migrations
  scripts/seed.py   # dev seed script (downloads Picsum images, uploads via API)
  static/index.html # dashboard
  tests/

pi/
  camera.py         # photo capture
  upload.py         # upload to backend
  cleanup.py        # prune old local photos

data/photos/        # stored image files (gitignored)
docs/               # design documents and roadmap
```

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/photos` | Upload photo + metadata JSON |
| `GET` | `/photos` | List photos (`?start=&end=` filter) |
| `GET` | `/photos/{filename}` | Serve image file |
| `POST` | `/photos/{photo_id}/notes` | Create note linked to photo |
| `GET` | `/photos/{photo_id}/notes` | List notes for photo |
| `PUT` | `/notes/{note_id}` | Update note |
| `DELETE` | `/notes/{note_id}` | Delete note |

Notes store normalized image coordinates (`x`, `y` in `[0.0, 1.0]`).

## Dashboard features

- Photo timeline with optional time-range filter
- Click a photo to open it in a modal; arrow keys to navigate
- A/B comparison: select two photos and view side by side
- Flicker comparison: toggle or auto-flicker between A and B to spot changes
- Timelapse: play/pause, prev/next, speed control
- Notes: click on a photo to pin a note at that position; edit and delete notes

## Roadmap

See `docs/roadmap.md`. Planned stages after the current dashboard foundation:

1. ~~Photo capture, upload, storage~~ (done)
2. ~~Dashboard: timeline, comparison, timelapse, notes~~ (done)
3. Simple image metrics (green area, canopy coverage, blur detection)
4. Decision support rules
5. ML / computer vision experiments
