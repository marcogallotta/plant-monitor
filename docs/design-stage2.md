# Plant Tracking System - Stage 2 Design

## Goal

Build a basic photo review dashboard on top of Stage 1 photo capture/upload/storage.

Stage 2 makes stored photos usable for visual review, comparison, playback, and notes.

Stage 2 is the first stage where Postgres is introduced.

## Scope

Stage 2 includes:

- Postgres database
- photo records in the database
- note records linked to photos
- note positions on photos using normalized image coordinates
- seed script that downloads a few placeholder images from Picsum
- seed script uploads those images through `POST /photos`
- backend endpoint to list stored photos
- backend endpoint to list stored photos by time range
- backend endpoint to serve individual stored photo files
- one simple HTML dashboard page
- photo timeline browsing
- two-photo comparison
- quick flicker/toggle comparison between two selected photos
- simple timelapse-style image playback
- basic note-taking linked to photos

Stage 2 does not include:

- plant/batch tracking
- sensor ingestion
- image metrics
- ML
- alerts
- automated analysis
- irrigation
- polished commercial dashboard

## Storage model

Image files still live on disk under:

```text
data/photos/
```

Postgres stores structured records for photos and notes.

The database is the source of truth for photo metadata and notes.

The filesystem is the source of truth for image bytes.

## Placeholder images

Use seeded Picsum URLs for fake test images.

Initial placeholder images:

```text
https://picsum.photos/seed/plant-test-001/1920/1080
https://picsum.photos/seed/plant-test-002/1920/1080
https://picsum.photos/seed/plant-test-003/1920/1080
```

These are not plant photos. They are only for testing upload, listing, display, comparison, notes, and playback.

## Seed script

Add a development script that:

1. downloads 3 placeholder images from Picsum
2. creates matching JSON metadata
3. uploads each image and metadata pair through `POST /photos`

The script should not write directly into `data/photos/`.

Seeded photos should look like normal uploaded photos to the backend.

## Database model

### photos

Stores one row per uploaded photo.

Fields:

- `id`
- `filename`
- `captured_at`
- `storage_path`
- `metadata_path`
- `created_at`

Rules:

- `filename` is unique
- `captured_at` is indexed
- uploaded image files remain stored on disk
- photo metadata is stored in Postgres, even if the original sidecar JSON is also kept on disk

### photo_notes

Stores notes linked to a photo.

Fields:

- `id`
- `photo_id`
- `note_text`
- `x`
- `y`
- `created_at`
- `updated_at`

Rules:

- `photo_id` references `photos.id`
- `x` and `y` are normalized image coordinates
- `x` must be between `0.0` and `1.0`
- `y` must be between `0.0` and `1.0`

Normalized coordinates mean:

```text
x = 0.0 is left edge
x = 1.0 is right edge
y = 0.0 is top edge
y = 1.0 is bottom edge
```

A note in the center of the image is:

```json
{
  "x": 0.5,
  "y": 0.5
}
```

## Backend API

### Upload photo

Existing endpoint:

```text
POST /photos
```

Stage 2 change:

- still stores image and metadata on disk
- also creates or updates the `photos` database record
- repeated upload of the same filename must not create duplicate database rows

### List photos

```text
GET /photos
```

Returns stored photos sorted by capture time.

Optional query parameters:

- `start`
- `end`

Example:

```text
GET /photos?start=2026-05-26T10:00:00Z&end=2026-05-26T12:00:00Z
```

Example response:

```json
[
  {
    "id": 1,
    "filename": "2026-05-26T103000Z.jpg",
    "captured_at": "2026-05-26T10:30:00Z",
    "url": "/photos/2026-05-26T103000Z.jpg"
  }
]
```

### Get photo file

```text
GET /photos/{filename}
```

Serves a single stored image file from `data/photos/`.

This endpoint must only allow valid stored photo filenames.

### Create note

```text
POST /photos/{photo_id}/notes
```

Request:

```json
{
  "note_text": "Leaf tips look slightly dry",
  "x": 0.42,
  "y": 0.61
}
```

Creates a note linked to a photo.

### List notes for photo

```text
GET /photos/{photo_id}/notes
```

Returns notes linked to that photo.

### Update note

```text
PUT /notes/{note_id}
```

Updates note text and/or position.

### Delete note

```text
DELETE /notes/{note_id}
```

Deletes a note.

## Dashboard

One simple HTML dashboard page served by FastAPI.

This should be usable, but not polished.

Required features:

### Photo timeline

- list stored photos in capture-time order
- allow optional time-range filtering
- click a photo to view it larger

### Two-photo comparison

- select photo A
- select photo B
- show both side by side

### Flicker comparison

- quickly toggle between selected photo A and photo B
- button and/or keyboard shortcut is enough
- purpose is to spot visual changes between two images

### Timelapse playback

- play a selected sequence of photos in order
- this is browser playback of still images
- no MP4/video generation
- basic controls:
  - play/pause
  - previous/next
  - speed if easy

### Notes

- user can click on a photo to create a note at that image location
- note stores normalized `x` and `y`
- notes display on or near the relevant photo
- notes can be edited and deleted

## Acceptance criteria

Stage 2 is done when:

- Postgres runs as part of the local backend stack
- uploaded photos create `photos` database records
- repeated upload of the same filename does not create duplicate photo rows
- 3 placeholder images can be seeded from Picsum through `POST /photos`
- stored photos can be listed through the API
- stored photos can be filtered by time range
- individual photo files can be served safely
- dashboard displays stored photos in time order
- user can select two photos and compare them side by side
- user can flick/toggle between two selected photos
- user can play a simple timelapse-style sequence
- user can create notes linked to photo positions
- notes persist in Postgres
- notes can be listed for a photo
- notes can be edited and deleted
- no plant/batch model is added
- no sensors, image metrics, ML, or alerts are added
