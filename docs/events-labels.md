# Stage 4 Design — Events and Photo Labels

## Core distinction

Events and labels are different things.

### Events

Events are **actions that happened**.

Examples:

- watered
- fed liquid
- fed worm castings
- harvested
- potted up
- propagated

An event answers:

```text
What did I do?
When did it happen?
What plant/location/photo was it related to?
```

Events may be linked to:

* nothing/global
* one or more growing units
* a location
* one or more photos
* optional note text

Events are history/log entries. They are not simple toggle state.

### Labels

Labels are **descriptive tags on a photo**.

Examples:

* aphids
* yellowing
* mildew
* damage
* new growth
* recovery
* looks worse
* looks better
* watch

A label answers:

```text
What is this photo showing?
```

Labels are reversible. If a label is wrong, click it off.

## Design decision for now

Support **photo-level labels first**.

Do not do note-level labels yet.

Later, if needed, labels can also attach to specific notes/regions.

## Photo labels UI

In the photo modal:

* show labels as chips
* selected labels are active
* clicking inactive label adds it to the photo
* clicking active label removes it from the photo
* save immediately
* show small saving/error status
* no Save button

For now, use existing labels from the backend.

Later, add:

* searchable label input
* create new label from search field
* common labels shown as quick chips

## Event UI

Keep events separate from labels.

There should be two event entry points:

### Global Events panel

Used for actions not necessarily tied to one photo.

Examples:

```text
Fed all balcony herbs
Watered everything
Added worm castings to basil and chilli
```

### Photo modal event UI

Used when the event is related to the current photo.

Examples:

```text
Potted up this plant
Harvested this plant
Propagated from this cutting
```

This creates a real event linked to the current photo.

## What not to do

Do not use photo labels for care actions like:

* watered
* fed liquid
* potted up
* harvested

Those are events.

Do not use events for visual classifications like:

* aphids
* yellowing
* mildew
* damage

Those are labels.

## Backend model

Keep:

```text
events
event_photos
event_growing_units
```

For labels:

```text
labels
photo_labels
```

Current photo-level label model is fine for now.

## API

Labels:

```text
GET /labels
POST /photos/{photo_id}/labels/{label_id}
DELETE /photos/{photo_id}/labels/{label_id}
```

Photos:

```text
GET /photos
```

should include:

```json
"labels": [{"id": 1, "name": "aphids"}]
```

Events:

```text
POST /events
GET /events
```

Events remain the care/action log.

## Acceptance criteria

* photo modal shows photo labels
* labels can be toggled on/off
* labels are descriptive observations, not care actions
* events remain separate action records
* global Events panel still works
* photo-linked events are still possible
* no note-level labels yet
* no region-level labels yet
