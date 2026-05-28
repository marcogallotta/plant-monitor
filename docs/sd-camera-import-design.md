# Design: easier SD / camera import on Ubuntu

## Goal

Replace the current browser folder-picker SD import flow with a backend-driven camera/card scanner.

Desired user flow:

```text
Plug in Sony RX100V / SD card
Open dashboard
Click "Scan camera/card"
See thumbnails from the mounted card/camera
Select photos
Click "Import selected"
```

The user should not have to manually open a browser file picker, navigate to `DCIM`, and select a folder.

## Current state

Relevant files:

- `backend/static/index.html`
  - SD import panel currently contains a hidden `<input type="file" webkitdirectory>`.
  - The visible button says `Choose folder`.
- `backend/static/sdImport.js`
  - Handles browser `File` objects from the folder picker.
  - Filters JPG/JPEG/ORF/ARW.
  - Builds thumbnails in the browser.
  - Extracts embedded JPEGs from RAW files in browser JS.
  - Uploads selected items through `/manual-photos`.
- `backend/static/sdImportCore.js`
  - Contains reusable logic: importable extension checks, RAW checks, camera filename sorting, session-boundary detection, embedded JPEG scan, timestamp derivation, FormData construction.
- `backend/app/main.py`
  - FastAPI app and photo upload endpoints live here.
  - `/manual-photos` stores uploaded JPEG bytes into `data/photos`, creates a `Photo` row, preserves `original_filename`, and uses source `manual`.
- `docker-compose.yml`
  - Backend currently mounts only:
    - `./backend:/app`
    - `./data/photos:/app/data/photos`
  - Therefore the backend container cannot see host-mounted SD cards/cameras yet.

The current limitation is architectural: browser JS can only access user-selected files. It cannot freely scan `/media/marco/...`. The backend can scan mounted media, but only if the host media directory is mounted into the backend container.

## Decision

Implement an **on-demand backend scanner**, not a daemon, for v1.

The normal import flow should become:

```text
Frontend button -> GET /camera-import/scan
Backend scans whitelisted mounted media roots
Backend returns candidate photo list + thumbnail URLs
Frontend renders selection grid
Frontend POSTs selected opaque file IDs to /camera-import/import
Backend copies/imports selected files
```

No daemon is required for v1. A daemon or hotplug watcher is only useful later if we want automatic detection immediately when a camera/card is inserted.

## Non-goals for v1

- Do not implement Sony Wi-Fi import.
- Do not implement a laptop daemon.
- Do not require udev rules.
- Do not expose arbitrary host paths to the browser.
- Do not allow the frontend to submit arbitrary filesystem paths.
- Do not preserve original RAW files in the photo archive. Preserve the current behaviour: store a JPEG representation and keep the camera filename in `original_filename`.
- Do not replace the existing manual upload flow.
- Do not remove the current browser folder-picker immediately; keep it as a fallback until the backend scanner is stable.

## Host / Docker mounting design

Add a read-only host media mount to the backend service.

Conceptually:

```yaml
backend:
  environment:
    IMPORT_MEDIA_ROOTS: /host-media
  volumes:
    - ./backend:/app
    - ./data/photos:/app/data/photos
    - ${HOST_MEDIA_ROOT:-/media/marco}:/host-media:ro
```

For the user's laptop, `/media/marco` is the likely mount root for SD cards and USB mass-storage cameras.

Optional later root for GVFS/PTP mounts:

```text
/run/user/1000/gvfs
```

But GVFS inside Docker can be awkward. The primary supported v1 path should be SD card reader or camera mounted as mass storage under `/media/marco`.

## Backend API

Add a new camera import API namespace. Suggested paths:

### `GET /camera-import/scan`

Scans configured import roots and returns importable photo candidates.

Query parameters:

- `include_imported: bool = false`
  - Default false means do not show already-imported files as selectable candidates.
  - The response may still include an imported count.
- `limit: int = 1000`
  - Hard cap to prevent accidentally scanning huge disks.

Response shape:

```json
{
  "sources": [
    {
      "id": "src_...",
      "label": "SONY_SD",
      "root": "/host-media/SONY_SD",
      "candidate_count": 183
    }
  ],
  "candidates": [
    {
      "id": "file_...",
      "source_id": "src_...",
      "source_label": "SONY_SD",
      "filename": "DSC01234.ARW",
      "relative_path": "DCIM/100MSDCF/DSC01234.ARW",
      "extension": ".arw",
      "size_bytes": 24312211,
      "mtime_ms": 1779961234000,
      "captured_at": "2026-05-28T14:20:34Z",
      "captured_at_source": "mtime",
      "is_raw": true,
      "already_imported": false,
      "thumbnail_url": "/camera-import/thumbs/file_..."
    }
  ],
  "importable_count": 183,
  "already_imported_count": 42,
  "warnings": []
}
```

Notes:

- `id` must be opaque. Do not return raw host paths as import handles.
- `relative_path` is okay for display only.
- `root` in `sources` is acceptable for local debugging, but it can be omitted if preferred.
- Sort candidates newest first, preferably by `mtime_ms DESC, filename DESC`.
- The frontend can reuse `detectSessionBoundary()` using `mtime_ms` to auto-select the latest batch.

### `GET /camera-import/thumbs/{file_id}`

Returns a JPEG thumbnail/preview for one scanned file.

Behaviour:

- For JPEG/JPG source files: return a downscaled JPEG preview, or return the original file initially if speed is preferred.
- For ARW/ORF: extract the largest embedded JPEG and return it.
- Use `Cache-Control: private, max-age=300` or similar.
- Return `404` if the file ID is unknown or expired.
- Return `415` if the source file type is unsupported.
- Return `422` if a RAW file contains no embedded JPEG preview.

### `POST /camera-import/import`

Imports selected files.

Request shape:

```json
{
  "file_ids": ["file_...", "file_..."],
  "photo_type": "overview",
  "location_id": null,
  "growing_unit_ids": [],
  "note_text": null
}
```

Response shape:

```json
{
  "created": [
    {
      "file_id": "file_...",
      "photo_id": 123,
      "filename": "0b7f...jpg",
      "original_filename": "DSC01234.ARW"
    }
  ],
  "skipped": [
    {
      "file_id": "file_...",
      "reason": "already_imported",
      "original_filename": "DSC01233.JPG"
    }
  ],
  "failed": [
    {
      "file_id": "file_...",
      "reason": "raw_preview_not_found"
    }
  ]
}
```

Import should be partial-success, not all-or-nothing. If one RAW file fails, the rest should still import.

## Backend implementation design

### New module

Create a dedicated module instead of stuffing all scanner logic into `main.py`.

Suggested file:

```text
backend/app/camera_import.py
```

Responsibilities:

- Read configured media roots.
- Discover mounted sources.
- Recursively scan candidate files.
- Build opaque file IDs.
- Maintain short-lived scan cache.
- Serve thumbnails.
- Import selected files.
- Extract embedded JPEGs from RAW files.

`main.py` can import and register an `APIRouter` from this module.

### Config

Add environment-driven config:

```text
IMPORT_MEDIA_ROOTS=/host-media
IMPORT_SCAN_MAX_FILES=1000
IMPORT_SCAN_CACHE_TTL_SECONDS=600
IMPORT_THUMB_CACHE_DIR=data/import-thumbs
```

Defaults:

- `IMPORT_MEDIA_ROOTS` default empty or `/host-media`.
- `IMPORT_SCAN_MAX_FILES` default `1000`.
- `IMPORT_SCAN_CACHE_TTL_SECONDS` default `600`.
- `IMPORT_THUMB_CACHE_DIR` optional; memory-only thumbnails are acceptable for v1, but disk cache is better for RAW previews.

### Root safety

Only scan whitelisted roots from `IMPORT_MEDIA_ROOTS`.

For every discovered path:

1. Resolve the path.
2. Confirm it is a regular file.
3. Confirm it is under one configured root.
4. Reject symlinks that resolve outside the root.
5. Accept only extensions:
   - `.jpg`
   - `.jpeg`
   - `.arw`
   - `.orf`
6. Skip unreadable files with a warning, not a crash.

The frontend must never send filesystem paths. It should only send opaque file IDs returned by the latest scan.

### File IDs and scan cache

Use an in-process scan cache for v1.

Cache shape conceptually:

```text
scan_cache[file_id] = {
  path,
  root,
  source_label,
  filename,
  size_bytes,
  mtime_ns,
  is_raw
}
```

File ID generation:

- Use a stable opaque ID generated from resolved path + size + mtime.
- Prefer HMAC with an app-local secret if available.
- Do not make the file ID a raw path or base64 path.

Before thumbnail/import:

- Look up `file_id` in cache.
- Re-stat the path.
- Confirm size and mtime still match the cached values.
- Confirm path still resolves under an allowed root.
- If validation fails, return expired/stale result.

This keeps v1 simple while preventing arbitrary path imports.

### Source discovery

Scan roots like `/host-media`.

Treat direct children as possible media sources:

```text
/host-media/SONY_SD
/host-media/NO NAME
/host-media/4621-0000
```

A source is considered useful if either:

- it contains a `DCIM` directory, or
- it contains importable photo files recursively.

Prefer scanning `DCIM` if present. Fall back to recursive source scan if no `DCIM` exists.

### Candidate sorting and latest batch

Backend should return candidates newest-first:

```text
mtime descending, then filename descending
```

Frontend should reuse the existing session gap rule from `sdImportCore.js`:

- Build timestamp list from `candidate.mtime_ms`.
- Call `detectSessionBoundary()`.
- Auto-select files before the first large gap.

This preserves the current latest-batch UX.

### Duplicate handling

For v1, match current behaviour:

- A file is already imported if `Photo.original_filename == candidate.filename`.

During scan:

- Mark `already_imported: true`.
- Hide already-imported files by default unless `include_imported=true`.

During import:

- Re-check duplicates before writing.
- If already imported, skip with reason `already_imported`.

Known limitation:

- Cameras can eventually reuse filenames after counter rollover or card reset.
- Future improvement: store a file fingerprint, e.g. `size + mtime + partial sha256`, but do not add this migration in v1 unless needed.

### JPEG/RAW import behaviour

The archive stores JPEG files only.

For source JPEG/JPG:

- Read the source bytes.
- Store them as a new UUID `.jpg` in `data/photos`.
- Preserve original camera filename in `Photo.original_filename`.

For source ARW/ORF:

- Extract the largest embedded complete JPEG.
- Store that JPEG as the archived `.jpg`.
- Preserve the RAW filename in `Photo.original_filename`, e.g. `DSC01234.ARW`.
- If no embedded JPEG is found, fail that item with `raw_preview_not_found`.

Use the same conceptual JPEG scanner already present in `sdImportCore.js`, but implemented in Python.

Current JS algorithm:

- Search for JPEG SOI marker: `FF D8 FF`.
- Search forward for EOI marker: `FF D9`.
- Track the largest complete JPEG segment.
- Return that segment.

For backend v1, reading the full RAW file for selected import is acceptable. RAW files are normally tens of MB, not GB.

### Captured timestamp

For v1, use this priority:

1. EXIF `DateTimeOriginal` if easy/reliable for JPEG.
2. Source file mtime.
3. Current time only as last resort.

Do not block the feature on perfect RAW EXIF parsing. The existing browser flow already falls back to `file.lastModified` for unsupported cases.

Return `captured_at_source` in scan results so the UI can optionally show whether it used EXIF or mtime.

### Shared photo creation helper

Refactor `upload_manual_photo()` so the common storage/database logic is reusable.

Create an internal helper conceptually like:

```text
create_photo_from_jpeg_bytes(
  db,
  image_bytes,
  original_filename,
  captured_at,
  source,
  photo_type,
  location_id,
  growing_unit_ids,
  note_text,
) -> Photo
```

Use it from:

- existing `/manual-photos`
- new `/camera-import/import`

The helper should preserve the current safety behaviour:

- write to temp file first
- rename atomically
- create DB row
- rollback and delete file on DB failure
- validate location/growing unit IDs

For camera import, set:

```text
source = "sd"
```

Also add `sd` to the source filter in `backend/static/index.html`:

```text
<option value="sd">SD / camera</option>
```

## Frontend design

### Keep fallback first

Do not delete the existing folder-picker path yet.

Update the SD import panel to show:

```text
[Scan camera/card] [Choose folder manually]
```

- `Scan camera/card` uses the new backend scanner.
- `Choose folder manually` keeps the existing `<input webkitdirectory>` behaviour as fallback.

### New API functions

Add to `backend/static/api.js`:

- `scanCameraImport()` -> `GET /camera-import/scan`
- `importCameraPhotos(body)` -> `POST /camera-import/import`

Thumbnail URLs can be used directly from scan response.

### Reuse existing SD grid UX

`sdImport.js` should support two modes:

1. browser-file mode, current implementation
2. backend-camera mode, new implementation

Do not duplicate the entire UI if avoidable. Normalize both modes into an internal `sdFiles` entry shape.

Current browser entries look like:

```text
{
  file,
  selected,
  isRaw,
  thumbUrl,
  uploadFile,
  capturedAt,
  tsBadge,
  sessionBreak
}
```

Backend entries can look like:

```text
{
  fileId,
  filename,
  selected,
  isRaw,
  thumbUrl,
  capturedAt,
  tsBadge,
  mtimeMs,
  alreadyImported,
  sessionBreak,
  mode: "backend"
}
```

For backend mode:

- `thumbUrl` comes from `candidate.thumbnail_url`.
- no browser `File` object is needed.
- upload/import calls `/camera-import/import`, not `/manual-photos`.

### Frontend scan flow

On `Scan camera/card` click:

1. Set status: `Scanning…`
2. Call `scanCameraImport()`.
3. Clear old `sdFiles` and old object URLs.
4. If no candidates:
   - show `No camera/card photos found.`
   - if imported count > 0, show `All N already imported.`
5. Build `sdFiles` from response candidates.
6. Auto-select latest batch using existing `detectSessionBoundary()` with `mtime_ms`.
7. Render thumbnails with existing grid.
8. Show count, controls, and import button.

### Frontend import flow

When `sdUploadSelected()` runs:

- If current mode is browser-file mode, preserve existing upload logic.
- If current mode is backend-camera mode:
  1. collect selected `fileId`s
  2. call `importCameraPhotos({ file_ids, photo_type, ... })`
  3. update each thumb status from response:
     - created -> checkmark
     - skipped -> skipped/grey or checkmark with tooltip
     - failed -> error
  4. call `_loadPhotos()` after successful imports

Keep the visible text user-level:

```text
17 imported, 2 skipped, 1 failed
```

## UI copy

Recommended SD panel controls:

```text
Scan camera/card
Choose folder manually
```

Status examples:

```text
Scanning…
Sony SD card found: 183 new photos, 42 already imported
No camera/card photos found.
All 42 photos already imported.
17 imported, 2 skipped, 1 failed
```

Do not expose backend path details in normal UI. Path details can go in console logs or backend logs.

## Tests

### Backend tests

Add tests around the new camera import module/routes.

Suggested file:

```text
backend/tests/test_camera_import.py
```

Required cases:

1. scan returns empty candidates when no media roots exist
2. scan finds `.jpg`, `.jpeg`, `.arw`, `.orf` recursively under a fake mounted root
3. scan ignores unsupported files like `.png`, `.mp4`, `.txt`
4. scan marks duplicate files using `Photo.original_filename`
5. scan hides imported files by default
6. scan includes imported files when `include_imported=true`
7. thumbnail endpoint returns JPEG for source JPEG
8. thumbnail endpoint extracts embedded JPEG from fake RAW bytes
9. thumbnail endpoint returns error for RAW with no embedded JPEG
10. import JPEG creates a `Photo` row with:
    - `source == "sd"`
    - `original_filename == camera filename`
    - supplied `photo_type`
    - supplied `location_id`
    - supplied growing unit links
11. import RAW stores extracted JPEG bytes and preserves RAW filename as `original_filename`
12. importing an already-imported filename returns skipped, not duplicate row
13. invalid/expired `file_id` returns failure or 404-style item result
14. symlink/path escape under mounted media root is rejected
15. partial batch success: one failed file does not prevent others importing

Test implementation should use `tmp_path` as a fake `/host-media` root and monkeypatch the import roots config.

### JS tests

Update existing tests:

- `backend/tests/js/sdImport.test.js`
- maybe add `backend/tests/js/cameraImport.test.js` if splitting logic

Required cases:

1. clicking scan calls backend scan API
2. scan results render thumbnail cards
3. latest batch is auto-selected using `mtime_ms`
4. no candidates shows correct status
5. already-imported-only response shows correct status
6. backend-mode import posts selected `file_id`s to `/camera-import/import`
7. backend-mode import updates thumb status for created/skipped/failed
8. existing folder-picker tests still pass

### Manual verification

Manual v1 verification:

1. Start app with media mount configured.
2. Insert SD card or plug camera in mass-storage mode.
3. Confirm host sees card under `/media/marco/...`.
4. Confirm backend container sees it under `/host-media/...`.
5. Open dashboard.
6. Click `Scan camera/card`.
7. Confirm thumbnails appear.
8. Confirm latest batch is auto-selected.
9. Import a small selection.
10. Confirm photos appear in main timeline with source `sd`.
11. Scan again.
12. Confirm imported files are skipped/marked imported.

## Implementation order for Claude

1. Add Docker/env config for read-only media root.
2. Add `backend/app/camera_import.py` with scanner, cache, thumbnail, import logic.
3. Refactor manual photo storage in `main.py` into a reusable helper.
4. Register new camera import router in `main.py`.
5. Add backend tests for scan, thumbnails, import, duplicates, and path safety.
6. Add `scanCameraImport()` and `importCameraPhotos()` to `backend/static/api.js`.
7. Update SD panel in `index.html` to show `Scan camera/card` and keep `Choose folder manually` fallback.
8. Extend `sdImport.js` to support backend candidate mode while preserving existing folder-picker mode.
9. Add/adjust JS tests.
10. Update README with media mount instructions and the new import workflow.

## Acceptance criteria

The feature is complete when:

- Normal workflow no longer requires opening the browser folder picker.
- With a card/camera mounted under the configured host media root, the dashboard can find photos by clicking `Scan camera/card`.
- JPEG and RAW candidates display thumbnails.
- The latest batch is auto-selected.
- Selected JPEGs import successfully.
- Selected ARW/ORF files import as extracted JPEG previews while preserving the original RAW filename.
- Imported files create normal `Photo` rows and appear in the main timeline.
- Duplicate camera filenames are skipped on later scans/imports.
- The browser never sends arbitrary filesystem paths to the backend.
- The backend refuses paths outside configured import roots.
- Existing manual upload and old folder-picker import still work.

## Later improvements

Only after v1 is working:

- Add automatic hotplug detection with udev/systemd or polling.
- Add a persistent import fingerprint column to avoid filename rollover issues.
- Add proper EXIF extraction for RAW timestamps via an external tool/library.
- Add a small thumbnail disk cache with cleanup.
- Add “import all latest batch” as a one-click shortcut.
- Add Sony Wi-Fi/PTP import as a separate source type if it proves reliable.
