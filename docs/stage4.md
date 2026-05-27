# Plant Tracking System — Stage 4 Design

## Lightweight Care Actions and Note Tags

## Goal

Stage 4 adds only the minimum structure likely to be useful in real use.

This is not a full event diary and should not become chore logging.

The system already has photos, photo notes, growing units, locations, manual uploads, and basic events.

Stage 4 should make two things easier:

1. logging a few useful care actions
2. tagging photo notes so visual/local observations can be found later

## Core principle

```text
Care actions = top-level quick logs
Visual/local observations = photo notes with optional tags
```

Do not manually log routine noise.

## Scope

Stage 4 includes:

- quick care-action buttons
- optional growing unit selection
- optional location selection
- optional note text
- note-level tags for photo notes
- basic review/filtering for care actions and note tags
- lightweight dashboard display

## Non-goals

Stage 4 does not include:

- full crop diary
- detailed watering logs
- detailed harvest logs
- routine move tracking
- structured quantities
- watering ml
- harvest grams
- fertiliser amounts
- diagnosis
- image metrics
- sensors/weather
- reminders/alerts

## Top-level care actions

Add quick actions for:

```text
fed_liquid
fed_worm_castings
watered
harvested
potted_up
other
```

Possibly later:

```text
propagated
```

but not now.

## Care action behaviour

A care action has:

- action type
- timestamp, default now
- optional growing units
- optional location
- optional note text
- optional linked photo

If no growing unit or location is selected, do not assume anything.

Example:

```text
fed_liquid — no unit selected
```

means only:

```text
I logged a general liquid feeding event.
```

It does not mean:

```text
All plants were fed.
```

## Why these actions

### fed_liquid / fed_worm_castings

These are likely useful because feeding cadence may matter later.

Possible future use:

```text
This unit has not been fed in a while.
```

### watered

Useful only as a rough marker, not as a full watering log.

There should be no pressure to log every watering.

### harvested

Useful only when it helps explain missing canopy or plant recovery.

There should be no pressure to log tiny harvests.

### potted_up

Useful because potting up can strongly affect growth, stress, and recovery.

### other

Escape hatch for anything meaningful.

## What not to log

Do not build the workflow around logging routine noise:

- daily moves
- sun-following moves
- normal watering
- normal harvest
- tiny pinches
- flower trimming
- casual inspection

The user may still log any of these manually under `other` if they matter.

## Photo note tags

Photo notes remain the main tool for visual/local observations because they have coordinates or boxes.

Add optional quick tags to notes.

Suggested note tags:

```text
issue
pest
fungal_mildew
yellowing
wilting
damage
new_growth
recovery
flowering
other
```

A note can have zero, one, or many tags.

The note text remains the real source of detail.

Examples:

```text
tag: pest
text: aphids here
box: selected area on image
```

```text
tag: yellowing
text: lower leaves yellowing
point/box: selected area on image
```

## Important split

Use care actions for general things done to plants:

```text
fed liquid fertiliser
added worm castings
watered
harvested
potted up
```

Use photo notes for visible things on the plant:

```text
aphids
mildew
yellowing
leaf damage
new growth
wilting
```

## Backend model

Existing `events` can be reused for care actions.

Recommended event types:

```text
fed_liquid
fed_worm_castings
watered
harvested
potted_up
other
```

Do not expand this list aggressively.

## Note tag storage

Add note tags either as:

### Option A — simple column

```text
photo_notes.tags JSON/text array
```

### Option B — normalized table

```text
photo_note_tags
- note_id
- tag
```

Recommendation: use the simpler approach unless the codebase already makes join tables easy.

## API changes

### Care actions

Reuse or lightly extend:

```text
POST /events
GET /events
```

Add filters if not already present:

```text
GET /events?event_type=&growing_unit_id=&location_id=&start=&end=
```

### Photo note tags

Extend note create/update:

```text
POST /photos/{photo_id}/notes
PUT /notes/{note_id}
```

Add optional:

```json
{
  "tags": ["pest", "yellowing"]
}
```

List notes should return tags.

## Dashboard changes

### Quick care panel

Add a small panel with buttons:

```text
Fed liquid
Fed worm castings
Watered
Harvested
Potted up
Other
```

Under the buttons:

- optional unit selector
- optional location selector
- optional note
- save/log button

Keep it fast. Do not make this a big form.

### Photo note UI

In the note panel, add quick tag toggles:

```text
issue
pest
fungal/mildew
yellowing
wilting
damage
new growth
recovery
flowering
other
```

The user can still just type text and ignore tags.

### Filters

Add simple filters later if easy:

- show notes tagged pest
- show notes tagged yellowing
- show fed events
- show potted-up events

## Usage rule

Do not ask or prompt the user to log routine actions.

The system should support logging, not nag.

## Future direction

After real usage, scan notes and event text to discover repeated terms:

```text
aphids
mildew
yellowing
fed
potted up
cut back
recovered
```

Then decide what deserves first-class structure.

Do not guess structure before usage proves it.

## Acceptance criteria

Stage 4 is done when:

- user can quickly log fed liquid
- user can quickly log fed worm castings
- user can quickly log watered
- user can quickly log harvested
- user can quickly log potted up
- each care action can optionally link to growing units/location/note/photo
- no selected unit/location means no assumption
- photo notes can have optional tags
- note tags are shown when viewing notes
- note tags can be edited
- existing photo notes still work
- existing events still work
- no structured quantities are added
- no reminders/alerts are added

## Suggested step breakdown

### 4.1 — Tighten event types for care actions

- Keep/reuse existing `events`.
- Add/confirm event types:
  - `fed_liquid`
  - `fed_worm_castings`
  - `watered`
  - `harvested`
  - `potted_up`
  - `other`
- Add tests for creating these event types.
- Do not add quantities.

### 4.2 — Quick care-action UI

- Add dashboard panel/buttons.
- Optional growing unit selector.
- Optional location selector.
- Optional note.
- Save to `/events`.
- If nothing selected, do not infer anything.

### 4.3 — Note tags backend

- Add note tags storage.
- Extend note create/update/list responses.
- Tests for tags create/update/list.

### 4.4 — Note tags UI

- Add tag toggles inside photo note panel.
- Tags work for point notes and box notes.
- Existing free-text notes still work unchanged.

### 4.5 — Basic review/filtering

- Filter events by type/unit/location/date.
- Filter or visually mark notes by tag.
- Keep this simple.

### 4.6 — Usage review checkpoint

- Use it for a week.
- Review what actually got logged.
- Decide whether to add propagation, reminders, quantities, or extraction later.

## Recommendation

Implement 4.1 to 4.4 only, then use it before doing 4.5+.
