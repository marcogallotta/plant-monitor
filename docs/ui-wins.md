# UI Wins

_Date: 2026-05-29_
_Status: Draft — ideas, not yet scoped_

A catalogue of UI improvements, rough-ordered by impact. Kept separate from feature design docs.

---

## 1. Filter bar

**Current state:** six dropdowns + two buttons, date inputs include time, no label filter, no visual indicator of active state.

**Wins:**

- **Date inputs → `type="date"`** (not `datetime-local`). You never need sub-day precision here. Simplifies both the input and the query — the backend already accepts ISO strings, so just append `T00:00:00` and `T23:59:59` client-side.
- **Add "Phone" to source options.** When bulk phone upload (see §3) lands, photos from it should be queryable separately from SD and legacy manual. Source value: `"phone"`.
- **Add a Label filter dropdown.** Currently you can't filter the grid by tag at all. A `<select id="filter-label">` populated from `GET /labels` (already loaded in `state.allLabels`) is a two-line addition to `index.html` and one extra param in `getPhotos()`.
- **Active-filter indicator.** When any filter is set, show a subtle dot or colour on the Filter button (or swap it to "Filtered"). Prevents the confusion of "why am I only seeing 3 photos?" after forgetting a filter is applied.
- **Auto-apply on change** (optional). Drop the Filter button; apply on `change` event for each control. Clears the two-step friction. The Clear button stays. Trade-off: an extra network call per interaction — fine given local data volumes.

---

## 2. Photo album / grid

**Current state:** `renderGrid()` renders every photo in one pass with no pagination. As the collection grows (and it will, once the Pi is running) this will get slow.

**Wins:**

- **Pagination or infinite scroll.** Simplest approach: render 60 at a time, append a "Load more" button (same pattern already used in SD import). Better: virtual scroll, but that's more work and low priority until the grid visibly lags.
- **Quick-filter chips above the grid.** Below the main filter bar, show a row of unit-name chips and the most-used label chips. Click to toggle. Selecting one adds it to the filter and re-renders — faster than opening a dropdown for the thing you filter by 80% of the time.
- **Caption shows unit name.** Right now the caption is just a timestamp. Add the growing unit name(s) when present (e.g. `"2026-05-22 · Thai basil"`). Lets you scan the grid without opening every photo.
- **Unclassified badge.** The status line already shows total count. Add `(N unclassified)` when any photos have no `photo_type` or no `growing_unit_ids`. Connects to the AI review flow — it's a one-liner using `state.allPhotos`.

---

## 3. Upload — de-emphasise single-photo and add bulk phone flow

**Current state:** "Upload photo" panel is prominently placed even though you barely use it. SD import is the primary path.

**Wins:**

- **Collapse "Upload photo" by default and push it lower.** It's already a collapsible panel; start it collapsed and move it below SD import. The SD panel should be first. No code change needed beyond reordering the HTML and setting the initial state.
- **Bulk phone upload.** The SD import panel already has a browser folder-picker path (`Choose folder`). Add a second button: "Choose photos (phone)" that opens a `<input type="file" multiple accept="image/jpeg">` — no `webkitdirectory`, just multi-select. Feed the selected files through the same `sdImportCore.js` logic (EXIF timestamp extraction, duplicate detection, sequential upload to `/manual-photos` with `source="phone"`). The SD grid UI reuses cleanly. This gives you the bulk-from-phone flow with minimal new code.
- **Rename "SD card import" to "Import"** now that it'll cover SD and phone. Or "Add photos" — more general.

---

## 4. De-clutter the homepage — panels

**Current state:** the page stacks: filters → sensor strip → Upload → SD import → Manage locations/units → Events → photo grid → Compare → Timelapse. Seven panels before you see a single photo.

**Wins:**

- **Tab navigation.** With the AI review panel (Stage 3) arriving soon, the page needs a structural change anyway. A tab bar fixes both problems at once:

  ```
  [ Gallery ]  [ Import ]  [ AI Review (14) ]  [ Events ]  [ Manage ]
  ```

  - **Gallery**: filters + photo grid + quick-filter chips. Compare/Timelapse live here, collapsed unless engaged.
  - **Import**: SD import panel + phone upload + legacy single upload.
  - **AI Review**: Stage 3 review panel + Stage 4 capture queue. Badge shows pending count.
  - **Events**: log event + event list.
  - **Manage**: locations + units CRUD. Used rarely; fine buried here.

  Implementation: pure CSS `display:none` toggle on tab content divs. No router needed. Active tab survives until page reload — `localStorage` can persist it if desired.

- **Compare and Timelapse — collapse until used.** If tabs aren't done yet, at minimum start these panels collapsed (the same toggle pattern the other panels already use). They're currently always-open and always empty, which looks like broken UI to a new visitor.

---

## 5. AI review (Stage 3) — UI placement notes

From the [Stage 3 design doc](design-stage3-ai-assisted-tagging.md):

- The review panel needs prominent placement — it's a core workflow, not a settings screen.
- The "AI Review" tab badge (unreviewed count) is the primary signal that work is waiting. It should be visible without scrolling.
- Keyboard shortcuts (`A` accept, `R` reject, `E` edit) mirror the modal pattern — keep them consistent.
- The unclassified badge on the photo grid (§2) doubles as a visual prompt to switch to the AI Review tab.

If tabs aren't built before Stage 3 lands, the review panel can sit above the photo grid temporarily, but it should be first-class in the layout, not an afterthought panel.

---

## 6. Other wins from code inspection

- **Label filter missing from filter bar** — noted in §1 but worth calling out separately. `state.allLabels` is already loaded at boot (`GET /labels`). Adding the filter is five lines of HTML and two lines in `loadPhotos()`.
- **Modal keyboard shortcuts undiscovered.** `←→` navigation and `F` for flicker are wired in `app.js:59–67` but the only UI hint is the zoom/pan/pin note at the bottom of the modal. Add `← → to navigate` to that hint line.
- **Filter location/unit dropdowns re-populate from cached state** but the cache is only refreshed on page load. If you add a unit in Manage and then try to filter by it without reloading, it won't appear. Either refresh `state.allLocations` / `state.allUnits` after `createLocation()` / `createUnit()`, or add a small "↺" refresh icon next to those dropdowns.
- **SD panel header click target inconsistency.** The `h2` has `onclick="toggleSdPanel()"` but the outer `div.upload-panel-header` does not — unlike the other panels where the whole header row is the click target. Small fix: move the `onclick` to the `div`.
- **No visual feedback on Filter / Clear.** After clicking Filter, nothing indicates the grid was refreshed. The status line updates but it's easy to miss. A brief flash or spinner on the photo grid would confirm the reload happened.
- **`multiple` select for growing units in the filter bar is absent** — the filter currently only supports a single unit. Multi-unit filter (`unit` param as a repeated query param) is a backend change too, so this is bigger, but worth noting.
