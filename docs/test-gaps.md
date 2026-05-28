# Test Gaps and Audit Report

Prepared 2026-05-28. Based on full read of all source files: `backend/app/main.py`, `backend/app/models.py`, `backend/static/*.js`, `backend/static/index.html`, `backend/tests/**`, and all compose files.

---

## 1. The Verify Stack — What It Is and Why It Causes DB Pollution

### What it is

`docker-compose.verify.yml` spins up two containers:

| Container | Image | DB |
|-----------|-------|----|
| `db-verify` | postgres:16 | `plantmonitoring_verify` (ephemeral, in-memory volume — no named volume declared) |
| `backend` | project backend image | talks to `db-verify` |

It exposes the backend on **port 8002** so a developer can visit `http://localhost:8002` and interact with a live UI while checking a feature.

### Why it does NOT pollute the real dev DB

The verify stack uses `plantmonitoring_verify`, not `plantmonitoring`. It is a completely separate Postgres instance. Anything written while `make verify-up` is running goes into the verify DB only.

`make verify-down` / `make verify-reset` both run `docker compose down -v`, which destroys the unnamed volume and wipes all data.

### The actual source of pollution

The verify stack itself is not the pollution source. The real risk is **running `make seed` or any other make target that defaults to `docker-compose.yml`** while the dev stack is up, because those targets talk to the `plantmonitoring` DB (port 8000 or 8001 from `.env`). If a developer ran:

```sh
make seed       # hits dev DB at http://backend:8000 — pollutes plantmonitoring
make migrate    # applies migrations to dev DB
```

while meaning to target the verify stack, that is the pollution path.

A secondary pollution path: if someone has `make up` running and they browse `http://localhost:8001` (or whatever `BACKEND_PORT` is) instead of `http://localhost:8002`, they are writing to the real dev DB.

### Is the verify stack necessary?

Its only purpose is providing a live browser target for manual UI verification. If the JS test suite is made comprehensive enough (see section 4), the verify stack becomes redundant for all functional checks. The only remaining use case would be visual/CSS spot-checking, and even that can be eliminated with snapshot or screenshot tests.

**Recommended fix:** once the JS tests described in section 4 are added, remove `docker-compose.verify.yml` and its Makefile targets entirely. Replace `make verify-up` with `make test-js` as the definitive check before marking work done.

---

## 2. UI Bugs — The Event Log / `potted_up` Display Issue

### Where the rendering happens

`backend/static/events.js` lines 93–124, the `loadEvents()` function. This is the only place event data is rendered to the DOM.

The key line is:

```js
typeSpan.textContent = ev.event_type.replace(/_/g, ' ');
```

### What this produces for each event type

| `event_type` (backend value) | Rendered text |
|------------------------------|---------------|
| `fed_liquid` | fed liquid |
| `fed_worm_castings` | fed worm castings |
| `watered` | watered |
| `harvested` | harvested |
| `potted_up` | potted up |
| `other` | other |

The underscore-to-space replacement is correct. `potted_up` → `potted up` is the expected result, and the dropdown option label in `index.html` (line 219) also reads `Potted up`.

**There is no display bug in the rendering logic itself.**

However, there are two related issues that could explain why "potted up" appears to show up incorrectly:

#### Issue A: The event log only loads on panel open, not after a `logEvent()` call from a different context

`loadEvents()` is called:
1. When the events panel is toggled open (`toggleEventsPanel()`).
2. After `logEvent()` succeeds (within the events panel).

It is **not** called after `modalLogEvent()` succeeds. So if someone logs an event from the modal's "+ event" button and then opens the events panel, the list refreshes correctly on open. This is not broken but it is easy to miss.

#### Issue B: `modalLogEvent()` uses a hardcoded event type select that is never reset to a default

In `modal.js` `modalLogEvent()`:

```js
var type = document.getElementById('modal-event-type').value;
```

The `modal-event-type` select (index.html lines 369–376) has `fed_liquid` as the first option, so it is always pre-selected. If a user logs `potted_up` via the modal and then opens the modal for a different photo, the select resets to `fed_liquid` (because `<select>` elements reset to their first option on DOM re-render only if explicitly cleared). **The modal's event type select is never cleared between photos.** So the select retains whatever value the user last chose, which could mean a `potted_up` event is accidentally logged for a subsequent photo without the user noticing.

This is a real UX bug, not a rendering bug. The fix is to reset `modal-event-type` to its first option in `showModalPhoto()` or `closeModal()`.

#### Issue C: The events panel `new-event-type` select also retains state after a successful `logEvent()`

In `logEvent()` (events.js line 66–84), after a successful post, the code clears `new-event-at`, `new-event-location`, unit selections, and `new-event-note` — but does **not** reset `new-event-type` to its default value. So the type dropdown stays on whatever the user last selected. This is minor but means the first dropdown value isn't a reliable indicator of what will be submitted next.

### No bug in the backend

`CARE_ACTION_TYPES` in `main.py` (line 572) and `CARE_ACTION_TYPES` in `events.js` (line 4) are in sync. The backend's `EventCreate` validator accepts all six types including `potted_up`. The schema test does not check `events` table columns — that is a gap (see section 3).

---

## 3. Missing Backend Tests

### 3.1 Schema tests

`test_schema.py` covers `photos`, `photo_notes`, `locations`, `growing_units`, and `photo_growing_units` but has **no assertions for the `events`, `event_growing_units`, or `event_photos` tables**.

Missing tests:
- `events` table exists
- `events` columns: `id`, `event_type`, `event_at`, `note_text`, `location_id`, `created_at`, `updated_at`
- `events.location_id` FK to `locations`
- `event_growing_units` table exists, columns `event_id`, `growing_unit_id`, FKs
- `event_photos` table exists, columns `event_id`, `photo_id`, FKs

### 3.2 `GET /photos` — missing `start`/`end` filter combination test

`test_list_serve.py` has `test_list_photos_filter_range` which tests `start` and `end` together. But `test_photo_listing.py` does not have the start+end combination. This is minor duplication rather than a gap.

### 3.3 `PUT /photos/{photo_id}` — `growing_unit_ids` with an empty list

`test_photo_listing.py` tests replace and clear-location, but there is no test for sending `growing_unit_ids: []` to explicitly clear all growing unit associations. The backend handles this case (the delete loop runs with an empty set), but it is not tested.

### 3.4 `PUT /photos/{photo_id}` — partial update (only `rotation`, no other fields)

Tested for `rotation` in isolation (line 184), but the `model_fields_set` logic means an update with only `rotation` must not touch `photo_type`, `location_id`, or `growing_unit_ids`. There is no test that verifies the existing `photo_type` is not cleared when only `rotation` is sent.

### 3.5 `POST /events` — all six valid event types are tested via parametrize

This is already covered by `test_create_event_valid_types` (parametrized). No gap here.

### 3.6 `GET /events` — filtering

The backend's `GET /events` endpoint has no query parameters and returns all events. There are tests for ordering. However, there is no test asserting that events linked to a deleted growing unit (cascade behaviour) behave correctly. This is edge-case.

### 3.7 Assistant API — `_event()` fixture uses `event_type="watering"` which is an invalid type

In `test_assistant_api.py` line 78, the `_event()` helper inserts directly into the DB with `event_type="watering"`. The backend's `EventCreate` validator would reject `"watering"` (it is not in `CARE_ACTION_TYPES`), but the DB has no CHECK constraint on `event_type`. The test data is therefore technically invalid and could mask bugs. The fixture should use a valid type like `"watered"`.

This is both a data quality bug in the test fixtures and evidence that **the DB has no CHECK constraint enforcing valid event types** — the backend relies entirely on Pydantic validation at the API layer.

### 3.8 `POST /manual-photos` — invalid `captured_at` format returns 422

This is tested. No gap.

### 3.9 `PUT /notes/{note_id}` — clearing `x2`/`y2` back to null

`update_note` in `main.py` only sets `note.x2` and `note.y2` if they are not `None` (lines 545–548). This means it is **impossible to clear a region note's `x2`/`y2` back to null via the API** — but there is no test that exposes this limitation. There should be a test sending `{"x2": null, "y2": null}` and verifying the result (which would reveal the current behaviour: the values are not cleared).

### 3.10 Rate limiter — window boundary exact-hit

`test_rate_limit_resets_after_window` backdates the window start by `_RATE_WINDOW + 1` seconds. There is no test for the exact boundary: a request at exactly `_RATE_WINDOW` seconds should reset (the condition is `>= _RATE_WINDOW`). Minor.

### 3.11 `GET /photos/{filename}` — serving manual-upload photos (UUID stem)

`GET /photos/{filename}` uses `_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.jpg$")`. UUID hex strings (32 lowercase hex chars) match this regex. There is a test for serving Pi-format photos (`test_serve_photo_returns_file_content`) and a manual upload serve test in `test_manual_photos.py`. The coverage is adequate, but the regex allows underscores and hyphens while UUID hex uses only `[0-9a-f]`. This is fine but undocumented.

### 3.12 `POST /events` — `potted_up` specifically accepted

The parametrize test covers all 6 types, so `potted_up` is tested. No gap.

---

## 4. Missing Frontend / JS Tests

The current JS test files are: `api.test.js`, `events.test.js`, `sdImportCore.test.js`, `utils.test.js`, `zoom.test.js`.

Completely untested JS modules: **`modal.js`**, **`notes.js`**, **`photos.js`**, **`timelapse.js`**, **`upload.js`**, **`sdImport.js`** (the DOM-heavy wrapper around `sdImportCore.js`).

### 4.1 `modal.js` — missing tests

All functions in `modal.js` are untested:

| Function | What to test |
|----------|-------------|
| `rotatePhoto(delta)` | Rotation wraps correctly (0→90→180→270→0, including negative delta). `state.currentRotation` is updated. |
| `showModalPhoto(index)` | `state.currentPhotoId` is set from `allPhotos[index].id`. Modal img src is updated. `state.currentRotation` is set from `p.rotation`. |
| `closeModal()` | `state.currentPhotoId` is null after close. `state.currentNotes` is cleared. |
| `toggleModalLogEvent()` | Panel toggles between display none and block. Status text is cleared. |
| `modalLogEvent()` | Calls `createEvent` with `{event_type, photo_ids: [currentPhotoId]}`. Note text is included when non-empty. Does nothing when `currentPhotoId` is null. **The modal event-type select is not reset between photos (bug from section 2, Issue B) — a test would catch a regression if the reset is added.** |
| `identityUpdate()` | Calls `updatePhoto` with correct body built from the select values. Updates `state.allPhotos[idx]`. Does nothing when `currentPhotoId` is null. |
| `showIdentityPanel(photo)` | Sets source, type select, location select, unit select selections. Shows/hides original-filename row. |

**Key missing test: `modalLogEvent` does not reset the event type select after submission.** A test that logs an event, simulates opening a second photo, and checks the select value would catch this.

### 4.2 `notes.js` — missing tests

| Function | What to test |
|----------|-------------|
| `renderPins()` | Point notes get `note-pin` class, positioned at `(x*100)%`. Rect notes get `note-rect` class with correct width/height. Selected note (matching `pendingNote.noteId`) gets `selected` class or dashed border. |
| `modalImgClick(e)` | When `wasDrag` is true, does nothing and clears `wasDrag`. Calls `_visualToStored` with normalised coords and opens create form. |
| `openCreateForm(x, y)` | Sets `pendingNote`. Clears note text. Sets title to "New note". Hides delete button. |
| `openCreateForm(x, y, x2, y2)` | Title is "New region note". |
| `noteSave()` | Calls `createNote` when no `noteId`. Calls `updateNote` when `noteId` exists. Includes `x2`/`y2` only when both are non-null. Does nothing when text is empty. |
| `noteDelete()` | Calls `deleteNote` with the correct ID. |
| `noteCancel()` | Clears `pendingNote`. Hides the note panel. |

### 4.3 `photos.js` — missing tests

| Function | What to test |
|----------|-------------|
| `loadPhotos()` | Calls `getPhotos` with parameters built from the DOM inputs. Sets `state.allPhotos`. Calls `renderGrid`. |
| `clearFilter()` | Clears all filter input values and calls `loadPhotos`. |
| `selectA(e, idx)` | Sets `state.photoA` and calls `stopPropagation`. |
| `selectB(e, idx)` | Sets `state.photoB`. |
| `flickerToggle()` | Calls `stopAuto` and toggles the flicker frame. |
| `flickerAuto()` | Starts `setInterval`. Stops when called again while timer is running. |
| `stopAuto()` | Clears the timer and resets button state. |

### 4.4 `timelapse.js` — missing tests

| Function | What to test |
|----------|-------------|
| `tlInit()` | With empty `allPhotos`: shows empty state, disables buttons. With photos: shows first frame, enables buttons. |
| `tlPrev()` | Wraps around from index 0 to last photo. |
| `tlNext()` | Wraps around from last photo to 0. |
| `tlPlayPause()` | Starts interval. Calling again stops it. Button text changes to "Pause" then back to "Play". |

### 4.5 `upload.js` — missing tests

| Function | What to test |
|----------|-------------|
| `toggleUploadPanel()` | Toggles `open` class and label text. |
| `submitManualUpload()` | With no file selected: sets status to "Choose an image first." — does not call `uploadPhoto`. With file: builds FormData with `image`, optional `captured_at` (as ISO string), optional `photo_type`, `location_id`, `growing_unit_ids`, `note_text`. Clears form inputs after success. Calls `_loadPhotos()` after success. |

### 4.6 `api.js` — gaps in existing tests

The existing `api.test.js` covers `getLocations`, `getPhotos`, `updatePhoto`, `createNote`, `deleteNote`. Missing:

| Function | Gap |
|----------|-----|
| `getGrowingUnits()` | Not tested (symmetric with `getLocations` but worth confirming URL). |
| `getNotes(photoId)` | Not tested — URL construction `/photos/{photoId}/notes`. |
| `updateNote(noteId, body)` | Not tested — PUT to `/notes/{noteId}`. |
| `createLocation(body)` | Not tested. |
| `createGrowingUnit(body)` | Not tested. |
| `createEvent(body)` | Not tested — especially the JSON body sent. |
| `getEvents()` | Not tested. |
| `uploadPhoto(formData)` | Not tested — uses `fetch` without JSON headers. |

### 4.7 `events.js` — gaps in existing tests

`events.test.js` tests `CARE_ACTION_TYPES` and `buildEventBody` thoroughly. Missing:

| Function | What to test |
|----------|-------------|
| `toggleManagePanel()` | Toggles `open` class and updates label text. |
| `toggleEventsPanel()` | Calls `loadEvents` when opening. |
| `createLocation()` | Reads `new-loc-name`, calls `apiCreateLocation`, clears inputs, shows status. Error path shows message. Empty name short-circuits. |
| `createUnit()` | Reads `new-unit-name`, calls `createGrowingUnit`, clears inputs. |
| `logEvent()` | Reads all event form fields, calls `createEvent`, clears fields (except type — bug), calls `loadEvents`. **Does not reset `new-event-type` after submission — a test would document and eventually enforce the correct behaviour.** |

### 4.8 `zoom.js` — existing tests are good

The `zoom.test.js` covers all rotation cases for `visualToStored` including clamping and corners. No meaningful gaps.

### 4.9 `utils.js` — existing tests are good

Covers `rotTransform`, `formatDate`, `populateSelect`. No gaps.

### 4.10 `sdImportCore.js` — existing tests are good

Comprehensive coverage of all exported functions. No meaningful gaps.

---

## 5. Recommended Fixes

### Priority 1: Stop DB pollution by clarifying the workflow

1. Add a warning comment to `docker-compose.verify.yml` and to the `verify-up` Makefile target making it explicit that this stack is for visual CSS checks only, never for functional verification.
2. Add a `VERIFY_DB` env-level assertion to the verify backend startup similar to the `plantmonitoring_test` assertion in `conftest.py` — though since the verify DB is ephemeral this matters less.
3. Long-term: remove the verify stack entirely once JS tests are sufficient (see Priority 3).

### Priority 2: Fix the two real UI bugs

**Bug B (modal event type not reset):** In `modal.js` `showModalPhoto()`, add:
```js
document.getElementById('modal-event-type').value = 'fed_liquid';
```
This ensures the event type resets to the default when navigating to a new photo.

**Bug C (events panel type not reset):** In `events.js` `logEvent()`, after the successful `createEvent()` call, add:
```js
document.getElementById('new-event-type').value = document.getElementById('new-event-type').options[0].value;
```

### Priority 3: Make the JS test suite comprehensive

Add the following test files (all using vitest + jsdom, same pattern as existing tests):

**`tests/js/modal.test.js`**
- Set up DOM with required elements before import (same pattern as `zoom.test.js`).
- Test every function listed in section 4.1, mocking `api.js` with `vi.mock('@/api.js')`.
- Specifically: a test that verifies `showModalPhoto()` resets `modal-event-type` to its first option (this test will fail until Bug B is fixed, which is the point).

**`tests/js/notes.test.js`**
- Render a minimal note-pins container, test `renderPins()` output for point and rect notes.
- Mock `api.js` functions and test `noteSave()`, `noteDelete()`, `noteCancel()`.

**`tests/js/photos.test.js`**
- Mock `getPhotos` and DOM filter inputs, test `loadPhotos()` builds the right query params.
- Test `clearFilter()` resets inputs.
- Test `selectA`/`selectB` update state.
- Test flicker functions with fake timers (`vi.useFakeTimers()`).

**`tests/js/timelapse.test.js`**
- Set up timelapse DOM elements.
- Test `tlInit()` with empty and non-empty `state.allPhotos`.
- Test `tlPrev()`/`tlNext()` wrap-around.
- Test `tlPlayPause()` starts/stops interval with fake timers.

**`tests/js/upload.test.js`**
- Mock `uploadPhoto` from `api.js`.
- Test `submitManualUpload()` with no file selected.
- Test `submitManualUpload()` builds FormData correctly.
- Test form fields are cleared after success.

**`tests/js/events-dom.test.js`** (separate from existing `events.test.js` which is pure logic)
- Set up events-panel DOM elements.
- Test `toggleManagePanel()` and `toggleEventsPanel()` toggle class and label.
- Test `createLocation()` with empty name short-circuits, with valid name calls `createLocation` API.
- Test `logEvent()` calls `createEvent` with correct body.
- Test that `new-event-type` is reset after a successful `logEvent()` call (fails until Bug C fixed).

**Extend `tests/js/api.test.js`:**
- Add tests for `getGrowingUnits`, `getNotes`, `updateNote`, `createLocation`, `createGrowingUnit`, `createEvent`, `getEvents`, `uploadPhoto`.

### Priority 4: Add missing backend schema tests

In `test_schema.py`, add:
- `events` table exists and has correct columns.
- `events.location_id` FK to `locations`.
- `event_growing_units` table exists with correct FKs.
- `event_photos` table exists with correct FKs.

### Priority 5: Fix the invalid test fixture

In `test_assistant_api.py`, change `_event()` helper from `event_type="watering"` to `event_type="watered"`. The current value is not in `CARE_ACTION_TYPES` and would be rejected by the API layer. This does not currently cause test failures (the helper writes directly to the DB, bypassing Pydantic validation), but it creates misleading test data.

### Priority 6: Add missing backend edge-case tests

- `PUT /photos/{photo_id}` with `growing_unit_ids: []` clears all associations.
- `PUT /photos/{photo_id}` with only `rotation` does not modify `photo_type`.
- `PUT /notes/{note_id}` with `{"x2": null, "y2": null}` — document current behaviour (does not clear, because the update handler only sets fields when non-null).

---

## 6. Summary: What Manual Verification Has Been Substituted For Automated Tests

Based on the codebase state, the following were verified manually via the verify stack but have no automated test coverage:

1. **Event log renders `potted_up` as "potted up"** — no JS test for `loadEvents()` DOM output.
2. **Modal event type persists across photo navigation** — no JS test for `showModalPhoto()` resetting selects.
3. **`logEvent()` clears the right form fields** — the type dropdown is not cleared; no test documents or enforces this.
4. **`submitManualUpload()` builds FormData with all optional fields** — tested manually, no automated test.
5. **Timelapse prev/next/play/pause** — no JS tests at all.
6. **Flicker auto-start/stop** — no JS tests.
7. **SD import panel: session boundary auto-selection** — not directly testable without the DOM flow, but `sdImportCore.js` logic is well-tested.
8. **Identity panel pre-fills from photo data** — no JS test for `showIdentityPanel()`.

---

## 7. Can the Verify Stack Be Eliminated?

Yes, once the JS tests listed in section 5 Priority 3 are added, `make test-js` will cover all functional behaviour that was previously checked via `make verify-up`. The verify stack can then be removed:

- Delete `docker-compose.verify.yml`
- Remove `verify-up`, `verify-down`, `verify-reset` from `Makefile`
- Remove `TEST_COMPOSE := ...` line (keep `VERIFY_COMPOSE` removal)
- Update `docs/internals.md` Docker Compose table to remove the verify stack row

The only thing the verify stack provides that automated tests cannot is visual/CSS layout checking. That remains a manual concern unless screenshot tests (e.g. Playwright) are added, which is out of scope for now.
