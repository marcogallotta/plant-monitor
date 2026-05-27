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
