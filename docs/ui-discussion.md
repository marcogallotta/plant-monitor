# UI Discussion

Open questions and ideas for the dashboard UI. Not a spec — capture intent so it's not forgotten.

---

## Log event with a photo attached

**Request:** when logging an event, be able to attach one or more photos to it at the same time.

**Current state:** the event form has type / when / location / units / note. Photos can be linked to events via `EventPhoto` (the DB join table already exists), but the log-event UI has no way to select photos.

**Ideas:**
- Add a photo picker to the log-event form — show recent thumbnails and let the user tick one or more.
- Alternative: from the modal (photo open), add a "link to event" or "log event for this photo" shortcut.
- The API `POST /events` already accepts `photo_ids: list[int]`, so no backend change needed.

---

## Comparison view: respect rotation

**Request:** when comparing two photos (A/B flicker), apply the same rotation as the single-photo modal view.

**Current state:** rotation is stored per-photo and applied in the modal, but the comparison/flicker view ignores it.

---

## Modal prev/next navigation

**Request:** add previous/next buttons inside the photo modal so the user can step through photos without closing and reopening.

**Current state:** arrow key navigation already exists (left/right keys), but there are no visible buttons for it.
