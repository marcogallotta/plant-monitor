# Plant Tracking System — Stage 6 Design

## SD Card Bulk Photo Upload

## Goal

Allow manual photos from a DSLR/mirrorless camera to be selected from a mounted SD card and uploaded to the backend via the dashboard.

## Core principle

```text
Frontend-only feature.
No new backend endpoints.
POST /manual-photos already handles everything needed.
```

## Scope

Stage 6 includes:

- SD card folder picker using `showDirectoryPicker()`
- recursive JPEG scan under the chosen folder
- EXIF `DateTimeOriginal` + `OffsetTimeOriginal` parsing via `exifr` (CDN)
- timezone fallback chain
- per-file upload to `POST /manual-photos`
- per-file status display
- `photo_type` default for the whole batch

## Non-goals

Stage 6 does not include:

- per-file `photo_type` override
- bulk categorisation UI
- `location_id` / `growing_unit_ids` assignment
- `note_text` per file
- duplicate detection based on `original_filename + captured_at`
- any new backend endpoints

## Timezone handling

`DateTimeOriginal` in EXIF is local camera time with no UTC offset unless `OffsetTimeOriginal` is also present.

Priority order:

1. If `OffsetTimeOriginal` is present, use it to build a proper offset string: `2026-05-20T14:32:01+02:00`
2. If absent, apply a configured timezone from the dashboard config (default `Europe/Rome`) and show an info badge: "Camera time interpreted as Europe/Rome"
3. If no config, upload with a warning badge: "Timezone unknown — time may be off"

Fallback: if EXIF is missing entirely, use `File.lastModified` and show a warning badge.

## Upload payload per file

```text
POST /manual-photos
  image:       <original file bytes, original filename>
  captured_at: ISO datetime with offset, e.g. "2026-05-20T12:32:01+00:00"
  photo_type:  batch default (see below)
```

`location_id`, `growing_unit_ids`, and `note_text` are omitted for now.

## photo_type default

`/manual-photos` accepts an optional `photo_type`. For SD card imports:

- default: leave blank (backend stores `null`)
- user can optionally pick a single default for the whole batch before uploading
- valid values: `overview`, `closeup`, `incident`, `comparison`, `harvest`, `propagation`, `other`

Bulk per-file categorisation is a later design (see below).

## Flow

1. User opens Upload tab in dashboard
2. Clicks **Choose folder** → `showDirectoryPicker()` opens
3. Dashboard scans recursively for `.jpg` / `.jpeg` files
4. Each file listed with: thumbnail, derived timestamp, original filename, timezone badge, checkbox
5. Optional: user picks a `photo_type` default for the batch
6. User checks files and clicks **Upload selected**
7. For each selected file, browser:
   - Reads EXIF via `exifr`
   - Derives `captured_at` using timezone priority chain above
   - POSTs to `/manual-photos`
8. Each row updates inline: uploading → done / error

## Dependencies

- `exifr` loaded from CDN — pure-JS EXIF parser, no build step

## Tests

- EXIF with `OffsetTimeOriginal` → correct UTC-anchored ISO string
- EXIF without offset → applies configured timezone, info badge set
- EXIF absent → `File.lastModified` used, warning badge set
- Upload payload construction (correct field names, `photo_type` value)
- Upload status transitions per file

## Acceptance criteria

Stage 6 is done when:

- user can pick an SD card folder from the dashboard
- all JPEGs under that folder are listed with thumbnails and derived timestamps
- timezone is handled correctly via the priority chain
- user can select a subset of files
- selected files upload to `/manual-photos` one by one
- each file shows per-file status (uploading / done / error)
- existing dashboard features are unaffected

## Suggested step breakdown

### 6.1 — Folder picker and file listing

- Add Upload tab to `static/index.html`
- Implement `showDirectoryPicker()` call
- Recursively collect `.jpg` / `.jpeg` files
- Render file list: filename, placeholder timestamp, checkbox
- No upload yet

### 6.2 — EXIF parsing and timestamp derivation

- Add `exifr` via CDN
- Read `DateTimeOriginal` and `OffsetTimeOriginal` per file
- Implement timezone fallback chain
- Show derived timestamp and timezone badge in file list
- Tests for timestamp derivation logic

### 6.3 — Upload

- Implement upload loop over selected files
- Build multipart payload: `image`, `captured_at`, `photo_type`
- Per-file status badges: uploading / done / error
- Tests for payload construction and status transitions

### 6.4 — Batch photo_type picker

- Add optional `photo_type` selector above the file list
- Applies to all selected files in the batch
- Defaults to blank

### 6.5 — Usage checkpoint

- Upload a real batch from SD card
- Check timestamps, photo_type, original_filename in the dashboard
- Decide whether bulk categorisation is worth designing next

---

## Later: bulk categorisation

Not in scope for Stage 6. Design separately.

Likely approach: after selecting files but before uploading, allow the user to assign `photo_type`, `location_id`, `growing_unit_ids` either to the whole batch or per-file with a fast keyboard-driven UI.

Possible patterns:

- select-all / select-subset then apply a value to the selection
- group files by date and assign type per group
- keyboard shortcut per row (e.g. `c` = closeup, `o` = overview)

Design this after seeing real bulk-upload usage.

---

## Later: location and growing unit tagging

Add `location_id` and `growing_unit_ids` to the upload payload once bulk categorisation UI is in place. Or we might just want to explore a bulk tag option after upload.

---

## Later: duplicate detection

`/manual-photos` generates UUID filenames so the backend has no duplicate detection.

If needed later, detect duplicates client-side by checking `original_filename + captured_at` against `GET /photos` before uploading, or add a backend endpoint for this. Do not add it now.
