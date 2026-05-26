# Plant Tracking System - V1 Design

## Goal

Build the minimum working photo pipeline.

Pi captures photo -> Pi uploads photo -> laptop backend writes photo to disk.

Nothing else.

## Scope

Includes:

- scheduled still-photo capture on Raspberry Pi
- full-resolution images
- local storage before upload
- sidecar JSON metadata beside each image
- upload to laptop backend
- backend storage under `data/photos/`
- retry after failed upload
- cleanup of successfully uploaded Pi copies after 7 days

Does not include:

- database
- frontend
- dashboard
- photo listing
- sensors
- plant or batch tracking
- notes
- image analysis
- alerts
- multiple devices
- camera positions

Use shell commands such as `ls`/`find` to inspect files.

## Backend

Fresh repo.

Stack:

- Python
- FastAPI

Endpoint:

- `POST /photos`

Backend behaviour:

- receive image plus metadata
- write image to `data/photos/`
- write uploaded metadata beside the image
- use timestamp filename as the V1 identity
- repeated upload of the same filename should not create duplicates
- return success only after the file and metadata are written

No database.

## Pi capture

Schedule:

- every 30 minutes
- 24 hours per day

For each capture, write:

- image file
- matching JSON metadata file

Example:

```text
2026-05-26T103000Z.jpg
2026-05-26T103000Z.json
```

Minimum metadata:

```json
{
  "captured_at": "2026-05-26T10:30:00Z",
  "filename": "2026-05-26T103000Z.jpg"
}
```

## Pi upload

Uploader scans local captured files and sends pending photos to `POST /photos`.

Rules:

- upload image plus metadata
- retry failed uploads later
- never delete unuploaded photos
- move successfully uploaded photos and metadata to `uploaded/`
- treat upload as complete only after backend success response

## Pi cleanup

Cleanup applies only to successfully uploaded photos in `uploaded/`.

Rules:

- keep uploaded Pi-local copies for 7 days
- remove uploaded Pi-local copies older than 7 days
- never remove unuploaded photos during normal cleanup

## Acceptance criteria

Done when:

- Pi captures full-resolution photos every 30 minutes
- each photo has matching JSON metadata
- Pi uploads photos to `POST /photos`
- backend stores photos under `data/photos/`
- backend stores uploaded metadata beside each image
- repeated upload does not create duplicates
- failed uploads retry later
- unuploaded photos are not deleted
- successfully uploaded Pi-local photos and metadata are moved to `uploaded/`
- uploaded Pi-local photos are removed after 7 days
- stored photos can be inspected with `ls`/`find`
