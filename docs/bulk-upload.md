# Plant Tracking System — SD Card Bulk Upload Design

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

Includes:

- SD card folder picker using `<input type="file" webkitdirectory>` (works on HTTP, compatible with Brave)
- flat JPEG/ORF/ARW listing from chosen folder, sorted by filename descending (DSLR filenames are sequential, so last = most recently shot; `lastModified` is unreliable on FAT32)
- ORF/ARW: embedded JPEG preview extracted client-side; original raw filename preserved for `original_filename`
  - ARW fast-path: read first 512 KB only (Sony preview is near start); fall back to full read if not found
  - ORF always full read (Olympus preview can be at 11 MB+)
- session boundary detection: time gap > 1 hour in `lastModified` between consecutive files; auto-selects latest session, loads 3 extra files past the break so the cutoff is visible
- paginated display: show last M files (default 20), "Load more" to show next M
- thumbnail grid — click to select/deselect
- EXIF `DateTimeOriginal` + `OffsetTimeOriginal` parsing via `exifr` (CDN)
- timezone fallback chain
- per-file upload to `POST /manual-photos`
- per-file status display
- `photo_type` default for the whole batch

## Non-goals

Does not include:

- subdirectory navigation
- per-file `photo_type` override
- bulk categorisation UI
- `location_id` / `growing_unit_ids` assignment
- `note_text` per file
- duplicate detection based on `original_filename + captured_at`
- any new backend endpoints

## Flow

1. User expands SD card import panel
2. Clicks **Choose folder** → `<input webkitdirectory>` opens
3. Browser reads all files; dashboard filters to `.jpg` / `.jpeg` / `.orf` / `.arw`, sorts newest first by filename descending (sequential camera numbering; `lastModified` is unreliable on FAT32)
4. Session boundary detected (time gap > 1 hour); latest session auto-selected; 3 extra files shown past the break for confirmation
5. Last M (default 20) shown as thumbnail grid; RAW thumbnails extracted async
6. Click a thumbnail to select it (highlighted); click again to deselect
7. **Load more** appends the next M thumbnails
8. Optional: user picks a `photo_type` default for the batch
9. **Import N selected** — for each selected file:
   - `captured_at`: EXIF `DateTimeOriginal` via timezone priority chain (stage 6.2); currently falls back to `File.lastModified`
   - POSTs to `/manual-photos`
10. Each thumbnail shows inline status overlay: uploading / ✓ done / ✗ error (hover for HTTP status)

## Thumbnail grid UX

- thumbnails are square, fixed size, aspect-ratio cropped
- selected state: highlighted border
- status overlay on each thumbnail after upload attempt: ✓ done / ✗ error; hover for HTTP status or error message
- "N selected" counter above the grid
- **Select all visible** and **Deselect all** buttons

## Timezone handling

`DateTimeOriginal` in EXIF is local camera time with no UTC offset unless `OffsetTimeOriginal` is also present.

Priority order:

1. If `OffsetTimeOriginal` is present, use it: `2026-05-20T14:32:01+02:00`
2. If absent, apply configured timezone (default `Europe/Rome`), show info badge
3. If no config, upload with warning badge: "Timezone unknown — time may be off"

Fallback: if EXIF is missing entirely, use `File.lastModified` and show a warning badge.

## Upload payload per file

```text
POST /manual-photos
  image:       <original file bytes, original filename>
  captured_at: ISO datetime with offset, e.g. "2026-05-20T12:32:01+00:00"
  photo_type:  batch default (optional)
```

`location_id`, `growing_unit_ids`, and `note_text` are omitted for now.

## photo_type default

- default: blank (backend stores `null`)
- user can pick a single default for the whole batch before uploading
- valid values: `overview`, `closeup`, `incident`, `comparison`, `harvest`, `propagation`, `other`

## Dependencies

- `exifr` loaded from CDN — pure-JS EXIF parser, no build step

## Tests

- EXIF with `OffsetTimeOriginal` → correct UTC-anchored ISO string
- EXIF without offset → applies configured timezone, info badge set
- EXIF absent → `File.lastModified` used, warning badge set
- Upload payload construction (correct field names, `photo_type` value)
- Upload status transitions per file

## Acceptance criteria

Done when:

- user can pick an SD card folder from the dashboard
- last M JPEG/ORF/ARW files shown as thumbnail grid, sorted newest first by filename
- ORF/ARW thumbnails extracted from embedded JPEG preview client-side
- session boundary auto-detected; latest batch auto-selected
- load more appends the next M
- click to select/deselect thumbnails
- timezone handled correctly via priority chain (stage 6.2)
- selected files upload to `/manual-photos` one by one
- per-file upload status shown on thumbnail (hover for error detail)
- existing dashboard features unaffected

## Suggested step breakdown

### 6.1 — Folder picker, thumbnail grid, and upload ✓ done

- `<input webkitdirectory>` folder picker (HTTP-compatible, works in Brave)
- filter to JPEG/ORF/ARW, sort newest first by filename descending
- ORF/ARW: extract embedded JPEG client-side (ARW fast-path 512 KB, ORF full read)
- session boundary detection; auto-select latest batch; show 3 past the break
- show last M (default 20) as thumbnail grid with Load more
- click to select/deselect; "N selected" counter; select all visible / deselect all
- "Import N selected" button; upload loop with per-thumbnail status overlay
- `captured_at` currently uses `File.lastModified` — replaced by EXIF in 6.2

### 6.2 — EXIF parsing and timestamp derivation ✓ done

- `exifr` loaded via CDN; parses `DateTimeOriginal`, `CreateDate`, `OffsetTimeOriginal`
- Priority chain: EXIF with offset → EXIF without offset (browser local time assumed) → `File.lastModified`
- Timestamp shown below filename in caption; colour indicates confidence:
  - green = offset present in EXIF
  - yellow = EXIF date but no offset (browser local timezone assumed)
  - red = no EXIF, using `File.lastModified`
- ORF not supported by exifr — always red/lastModified fallback
- Upload uses `entry.capturedAt`; falls back to `lastModified` only if EXIF not yet resolved

### 6.3 — Batch photo_type picker

- Optional `photo_type` selector above the grid
- Applies to all selected files in the batch
- Defaults to blank

### 6.4 — Usage checkpoint

- Upload a real batch from SD card
- Check timestamps, photo_type, original_filename in the dashboard
- Decide whether bulk categorisation is worth designing next


---

## Later: bulk categorisation

Not in scope. Design separately.

Likely approach: after selecting thumbnails but before uploading, assign `photo_type`, `location_id`, `growing_unit_ids` to the whole selection or per-file with a fast keyboard-driven UI.

Possible patterns:

- select subset then apply a value to the selection
- group by date and assign type per group
- keyboard shortcut per thumbnail (e.g. `c` = closeup, `o` = overview)

Design after seeing real bulk-upload usage.

---

## Later: location and growing unit tagging

Add `location_id` and `growing_unit_ids` to the upload payload once bulk categorisation UI is in place.

---

## Later: duplicate detection

`/manual-photos` generates UUID filenames so the backend has no duplicate detection.

If needed later, detect duplicates client-side by checking `original_filename + captured_at` against `GET /photos` before uploading, or add a backend endpoint. Do not add now.
