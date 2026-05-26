# Plant Tracking System — Stage 3 Design

## Evidence Identity, Manual Photos, and Basic Events

## Goal

Stage 3 turns the existing photo dashboard into a practical plant evidence system.

Stages 1 and 2 already provide photo capture/upload/storage, Postgres photo records, dashboard review, comparison, flicker/timelapse, and photo notes. Stage 3 should not rebuild that.

The new goal is:

```text
photo -> growing unit(s) -> location -> time -> source/type -> notes/events
```

This makes photos useful for balcony learning now and future nursery-style evidence later.

## Core idea

Do not force everything into either “individual plant” or “batch”. Real plants are messier than that.

Use one flexible concept:

```text
growing_unit
```

A growing unit is whatever level is useful to track.

Examples:

- Genovese basil plant 1 — individual
- Thai basil plant 1 — individual
- French tarragon mother plant — mother plant
- Chives clump — clump
- Mint pot — mixed/clump
- Lemongrass supermarket cuttings — batch now, clump later
- Hangjiao H4 chilli seedlings — batch
- 60cm dill/parsley/chives planter — container/mixed planter
- Propagation tray — tray/container

This avoids fake precision. Track at the level that is actually useful.

## Scope

Stage 3 includes:

- growing unit records
- simple flat location records
- manual photo upload/import
- photo source metadata
- photo type metadata
- linking photos to one or more growing units
- linking photos to a location
- dashboard filters by growing unit, location, source, and type
- photo detail view showing identity fields
- editing photo identity fields after upload
- basic structured events as the final part of the stage

## Non-goals

Stage 3 does not include:

- image metrics
- computer vision
- ML
- plant health diagnosis
- sensor ingestion
- weather ingestion
- irrigation control
- decision-support rules
- polished commercial UI
- QR labels
- nursery inventory management
- complex location nesting or garden mapping

## Data model

### growing_units

Represents an individual plant, clump, batch, tray, planter, mother plant, or mixed unit.

Fields:

- `id`
- `name`
- `unit_type`
- `species`
- `variety`
- `source`
- `started_at`
- `notes`
- `current_location_id`
- `created_at`
- `updated_at`

Initial `unit_type` values:

- `individual`
- `mother_plant`
- `clump`
- `batch`
- `container`
- `tray`
- `mixed`
- `other`

Rules:

- `name` is required.
- All other fields may be nullable.
- Do not over-police `unit_type`; it is for filtering and clarity.
- A unit may change in practical meaning over time. For example, lemongrass may start as a batch and later be treated as a clump.

### locations

Locations are simple flat labels for now.

Examples:

- Balcony
- South rail
- West windowsill
- Herb planter area
- Propagation tray area

Fields:

- `id`
- `name`
- `description`
- `created_at`
- `updated_at`

No nesting in Stage 3. If this becomes limiting later, locations can be redesigned.

### photos changes

Add fields to the existing `photos` table:

- `source`
- `photo_type`
- `original_filename`
- `location_id`

Initial `source` values:

- `pi`
- `manual`
- `seed`

Initial `photo_type` values:

- `overview`
- `closeup`
- `incident`
- `comparison`
- `harvest`
- `propagation`
- `other`

Rules:

- Existing Pi uploads default to `source='pi'`.
- Manual uploads use `source='manual'`.
- `photo_type` is optional.
- `location_id` is optional.
- Old unclassified photos must still display normally.

### photo_growing_units

A join table linking photos to zero, one, or many growing units.

Fields:

- `photo_id`
- `growing_unit_id`
- `created_at`

Why this exists:

- A Pi overview photo may show the whole balcony or many units.
- A close-up may show a mixed planter with dill, parsley, and chives.
- A photo may show a batch plus a selected individual.
- The system should not force one photo = one plant.

Rules:

- A photo may have no growing unit yet.
- A photo may have one growing unit.
- A photo may have multiple growing units.
- A photo may also have a location.

## Manual photo upload

Manual photo upload is central to Stage 3.

Add:

```text
POST /manual-photos
```

Accept multipart form data:

- image file
- optional `captured_at`
- optional `photo_type`
- optional `location_id`
- optional list of `growing_unit_ids`
- optional `note_text`

Backend behaviour:

- store image under `data/photos/`
- generate a safe backend filename
- preserve phone/camera filename in `original_filename`
- create a normal `photos` row
- set `source='manual'`
- link selected growing units
- link selected location if provided
- create an initial note if `note_text` is provided

Manual uploads must not require the Pi timestamp filename format.

## Backend API

### Growing units

```text
POST /growing-units
GET /growing-units
GET /growing-units/{id}
PUT /growing-units/{id}
```

Delete is not required unless trivial.

### Locations

```text
POST /locations
GET /locations
GET /locations/{id}
PUT /locations/{id}
```

Delete is not required unless trivial.

### Manual photos

```text
POST /manual-photos
```

Creates a manual photo and optional initial note.

### Photo classification update

```text
PUT /photos/{photo_id}
```

Allow updating:

- `photo_type`
- `location_id`
- linked `growing_unit_ids`

This allows old photos to be classified after upload.

### Photo listing filters

Extend existing:

```text
GET /photos
```

Optional filters:

- `source`
- `photo_type`
- `location_id`
- `growing_unit_id`
- existing `start`
- existing `end`

Photo responses should include:

- source
- photo type
- original filename
- location id/name
- linked growing unit ids/names/types

## Dashboard changes

Keep the current simple dashboard style. Do not redesign the whole frontend.

### Manual upload panel

Add a small form:

- image file
- captured_at, default now
- photo type
- location
- one or more growing units
- optional note text

Uploaded photos appear in the normal timeline.

### Filters

Add filters for:

- source
- photo type
- location
- growing unit
- date range

Unclassified photos should still appear when filters are blank.

### Photo detail identity panel

When opening a photo, show:

- captured_at
- source
- photo type
- original filename if present
- location if set
- linked growing units if set
- existing notes

Allow editing if practical:

- photo type
- location
- linked growing units

Existing zoom, note, comparison, flicker, and timelapse features should keep working.

## Structured events

Structured events are included in Stage 3, but they should be the final sub-stage after growing units, locations, manual photos, and filtering work.

Events should be simple records, not a complex journal.

Examples:

- watered
- harvested
- pinched/pruned
- moved
- potted up
- propagated
- stress noticed
- pest/mildew/yellowing noticed
- recovered/improved
- other

### events

Fields:

- `id`
- `event_type`
- `event_at`
- `note_text`
- `location_id`
- `created_at`
- `updated_at`

### event_growing_units

Join table:

- `event_id`
- `growing_unit_id`

### event_photos

Optional join table:

- `event_id`
- `photo_id`

Rules:

- An event may link to zero, one, or many growing units.
- An event may link to a location.
- An event may link to one or more photos.
- Keep the UI lightweight: quick-add event, select unit/location, optional note.

## Seed/demo data

Suggested locations:

- Balcony
- South rail
- West windowsill
- Propagation area

Suggested growing units:

- Thai basil plant 1 — individual
- Genovese basil plant 1 — individual
- French tarragon — mother plant
- Chives clump — clump
- Mint pot — mixed
- Lemongrass supermarket cuttings — batch
- Hangjiao H4 chilli seedlings — batch
- Dill/parsley/chives planter — container/mixed

Seed photos may remain placeholders, but they should exercise source/type/location/growing-unit links.

## Testing

Backend tests:

- create/list/get/update growing units
- create/list/get/update locations
- existing Pi upload still works
- Pi upload sets `source='pi'`
- manual photo upload stores file and creates photo row
- manual photo upload sets `source='manual'`
- manual photo upload preserves `original_filename`
- manual photo upload links one growing unit
- manual photo upload links multiple growing units
- manual photo upload links location
- manual photo upload can create initial note
- updating photo classification works
- filtering photos by source/type/location/growing unit works
- existing notes still work
- event creation works
- event can link to growing units/photos/location

Dashboard smoke tests:

- manual upload form exists
- source/type/location/growing-unit filters exist
- photo detail shows identity fields
- event quick-add UI exists after event sub-stage

## Acceptance criteria

Stage 3 is done when:

- growing units can be created, listed, viewed, and updated
- locations can be created, listed, viewed, and updated
- existing photos still display after migration
- existing Pi upload still works
- Pi photos have source `pi`
- manual photos can be uploaded through backend and dashboard
- manual photos use safe backend filenames
- manual photos preserve original filename metadata
- photos can link to zero, one, or many growing units
- photos can link to a location
- photos can be classified/reclassified after upload
- photo list can filter by source, type, location, growing unit, and date range
- photo detail shows source, type, location, and linked growing units
- structured events can be added as the final sub-stage
- events can link to growing units, locations, and photos
- existing notes, comparison, flicker, and timelapse still work
- no image metrics, sensors, ML, diagnosis, or irrigation control are added

## Suggested implementation order

Stage 3 is split into six sub-stages. Each sub-stage should have passing tests before moving on.

**3.1 — Schema & migrations**
- New tables: `growing_units`, `locations`, `photo_growing_units`
- New columns on `photos`: `source`, `photo_type`, `original_filename`, `location_id`
- Migration script and schema tests

**3.2 — Growing units & locations API**
- `POST/GET/GET{id}/PUT` for `growing_units` and `locations`
- Tests: create, list, get, update for each

**3.3 — Extend photo model, listing, and classification**
- Extend `GET /photos` with new filters (`source`, `photo_type`, `location_id`, `growing_unit_id`) and richer response fields (source, type, original filename, location, linked units)
- `PUT /photos/{id}` for reclassifying type/location/units after upload
- Tests: filtering, classification update, verify Pi upload still sets `source='pi'`

**3.4 — Manual photo upload**
- `POST /manual-photos`: safe backend filename, preserve `original_filename`, set `source='manual'`, link units/location, optional initial note
- Tests: file storage, photo row, source, original filename, unit linking, location linking, initial note

**3.5 — Dashboard identity, upload panel, and filters**
- Manual upload form (file, captured_at, type, location, units, note)
- Filters sidebar (source, type, location, growing unit, date range)
- Photo detail identity panel (show and edit type/location/units)
- Existing zoom, notes, flicker, comparison, and timelapse must keep working

**3.6 — Structured events**
- New tables: `events`, `event_growing_units`, `event_photos`
- Event API endpoints
- Quick-add event UI in dashboard
- Tests: event creation, linking to units/photos/location

Keep the implementation boring, small, and compatible with the existing simple app.
