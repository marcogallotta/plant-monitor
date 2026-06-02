# SD import — duplicate detection & scan handoff

Handoff for two recurring bugs. Diagnosis is verified against the running stack
(2026-06-02). No code/migration has been written yet — this doc is the design to
implement, not a record of work done.

---

## Issue 1 — "Choose folder" duplicate detection lists already-imported photos as new

### Root cause

The browser folder-picker and phone-picker decide "already imported?" entirely
client-side, from `state.allPhotos`:

- `sdImport.js:166-178` (`handleSdFolderInput`)
- `sdImport.js:234-246` (`handlePhoneFilesSelected`)

But `state.allPhotos` is only the **first page** of the **currently-filtered**
gallery — `loadPhotos()` fetches `limit: PAGE_SIZE` (default 60) at `offset: 0`
(`photos.js:77`). Any photo older than the first 60, or hidden by an active
filter, is invisible to the dedup, so the picker shows it as new.

Commit `59e25c8` (2026-06-01) tried to patch this with a backend backstop in
`/manual-photos` (`main.py:445`) that rejects a dupe when `original_filename`
**and** `original_size_bytes` both match. That stops most *DB* duplicates but:
- the UI still mislabels already-imported photos as new and re-uploads them;
- 45 existing rows have `original_size_bytes IS NULL`, so they bypass the match.

This is why it "keeps breaking": the client never had the full picture, and the
two dedup code paths (client vs. `/manual-photos`) can drift.

### Evidence

- Dev DB has exactly one real dup pair: `PXL_20260530_071822953.MP.jpg`
  (ids 125, 1414), **both created 2026-05-30 — before** the backstop existed.
- `select count(*) filter (where original_size_bytes is null)` = 45 of 984.

### Agreed design (scalable)

Chunked backend dedup check + a DB unique constraint as the real backstop. The
client check is UI-only; the unique index is what actually prevents dupes.

**Dedup key** (single-user app — no `user_id`):
`(original_filename, original_size_bytes)`

**Pre-import UI check**
- New endpoint, e.g. `POST /camera-import/check-imported`.
- Client sends the picked files in **chunks of 500** `{filename, size}`.
- Server returns each as `new` / `already_imported`, via an indexed
  `WHERE original_filename IN (...)` lookup (bounded by chunk, not library).
- Client builds its skip-set from the response instead of `state.allPhotos`,
  so pagination and filters become irrelevant.

**Import backstop**
- Add a **partial unique index**:
  `UNIQUE (original_filename, original_size_bytes) WHERE original_size_bytes IS NOT NULL`.
  Postgres treats NULLs as distinct, so legacy NULL-size rows won't false-collide.
- Insert path catches the unique violation and reports "already imported"
  (mirror the existing `IntegrityError` handling used for labels).

**Legacy NULL-size rows**
- Filename-only match → report as `possible_duplicate` (not auto-skipped).

**Anti-drift**
- `/manual-photos` and `/camera-import/import` and the new check endpoint must
  all derive their answer from **one shared helper**, so they can't diverge again.

**Migration caveat**
- The existing dup pair (ids 125/1414) must be de-duplicated **before** adding the
  unique index, or the migration will fail.

**Tests (write first)**
- vitest: picker dedups against the check-endpoint response, not `state.allPhotos`;
  correct skip-count when dupes live beyond page 1 / behind a filter.
- backend: chunked check returns correct new/already/possible_duplicate sets;
  unique index rejects a second insert with the same key; NULL-size rows allowed.

---

## Issue 2 — "Scan camera" finds nothing

### Root cause — stale container, not a code bug

The running `plant-monitoring-backend-1` mounts `/media` as **`rprivate`**, even
though `docker-compose.yml:41` correctly declares **`rslave`**. With `rprivate`,
SD-card mounts on the host never propagate into the container, so
`IMPORT_SCAN_PATH` (`/media/marco/4621-0000/DCIM/101MSDCF/`) resolves to an empty
ext4 mountpoint and the scan returns nothing.

### Why — a one-time startup race (already fixed in git)

- `a279dd4` (Jun 1 08:51) added `rslave` to compose.
- `c581445` (Jun 1 12:42:37) added `scripts/media-shared.service` and enabled it
  `--now`. The unit bind-mounts `/media` onto itself and marks it shared, and is
  ordered `Before=docker.service` (`WantedBy=docker.service`).
- The backend container came up Jun 1 12:42 CEST — the **same minute** the unit
  first ran — so it bound `/media` before it became shared, landing on `rprivate`.

Host side is now correct: `findmnt /media` shows `shared`; the exfat card is
mounted and visible (`100OLYMP`, `101MSDCF`). The unit is `enabled` + `active`.

### Fix

No code change. **Recreate the backend container once**, now that `/media` is
shared:

```sh
docker compose up -d --force-recreate backend
```

Then verify and test:
```sh
docker inspect -f '{{range .Mounts}}{{.Destination}} {{.Propagation}}{{println}}{{end}}' \
  plant-monitoring-backend-1            # expect: /media rslave
docker exec plant-monitoring-backend-1 ls /media/marco/4621-0000/DCIM/101MSDCF | head
curl -s localhost:8001/camera-import/scan | head   # expect candidates, not empty
```

On future reboots the unit runs before docker, so this is durable; the stale
container is the only leftover.

---

## Issue 3 — `CAMERA_IMPORT_HMAC_SECRET` unset → file IDs invalidated on reload

### Root cause

`camera_import.py:35-36` falls back to a per-process random secret when the env
var is unset:

```py
_hmac_secret_env = os.environ.get("CAMERA_IMPORT_HMAC_SECRET", "")
_HMAC_SECRET = _hmac_secret_env.encode() if _hmac_secret_env else os.urandom(32)
```

It is **not set** in `.env` or `docker-compose.yml`. The opaque file IDs handed to
the browser (`_make_file_id`, line 144) are HMAC'd with this secret. The dev
backend runs `uvicorn --reload`, so **every code edit restarts the worker with a
new random secret** — every file ID from the previous scan becomes invalid.
Symptom: after an edit (or any worker restart), thumbnails 404 and "Import
selected" fails with `not_found_or_expired` until the user re-scans.

### Fix

Set a fixed secret so IDs survive restarts:
- add `CAMERA_IMPORT_HMAC_SECRET` to `.env` (and pass it through in
  `docker-compose.yml` env, like the other vars at `docker-compose.yml:20-28`).
- generate once, e.g. `python -c "import secrets; print(secrets.token_hex(32))"`.
