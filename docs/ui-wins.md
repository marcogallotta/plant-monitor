# UI Wins

_Date: 2026-05-29_
_Status: Draft — ideas, not yet scoped_

A catalogue of UI improvements, rough-ordered by impact. Kept separate from feature design docs.

---

## 1. Filter bar

**Done:** date inputs → `type="date"`, "Phone" source option, label filter dropdown, active-filter indicator (green border + highlighted Clear button), auto-apply on change (Filter button removed), Clear resets all including label.

**Remaining:**

- **`multiple` select for growing units** — currently only one unit can be filtered at a time. Multi-unit filter needs a backend change (`unit` as a repeated query param). Bigger scope.

---

## 2. Photo album / grid

**Done:** caption shows unit name(s), unclassified badge in status line.

**Remaining:**

- **Pagination or infinite scroll.** Simplest: render 60 at a time, "Load more" button (same pattern as SD import). Hold until the grid visibly lags with Pi photos.
- **Quick-filter chips above the grid.** Row of unit-name and common label chips below the filter bar — one-click filtering without opening a dropdown. Good for the units you use 80% of the time.

---

## 3. Upload — bulk phone flow

**Done:** "Upload photo" panel renamed "Upload single photo", moved below SD import, starts collapsed. SD import panel renamed "Import photos", header click target fixed.

**Remaining:**

- **Bulk phone upload.** Add a "Choose photos (phone)" button to the Import panel — `<input type="file" multiple accept="image/jpeg">`. Feed files through the existing `sdImportCore.js` EXIF/upload logic with `source="phone"`. Reuses the SD grid UI.

---

## 4. De-clutter the homepage — panels

**Done:** Compare and Timelapse panels start collapsed; auto-expand Compare when A or B is selected.

**Remaining:**

- **Tab navigation.** With AI review (Stage 3) arriving soon, the page needs a structural change anyway:

  ```
  [ Gallery ]  [ Import ]  [ AI Review (14) ]  [ Events ]  [ Manage ]
  ```

  - **Gallery**: filters + photo grid + quick-filter chips. Compare/Timelapse live here, collapsed unless engaged.
  - **Import**: SD import panel + phone upload + legacy single upload.
  - **AI Review**: Stage 3 review panel + Stage 4 capture queue. Badge shows pending count.
  - **Events**: log event + event list.
  - **Manage**: locations + units CRUD.

  Implementation: pure CSS `display:none` toggle on tab content divs. `localStorage` can persist active tab.

---

## 5. AI review (Stage 3) — UI placement notes

From the [Stage 3 design doc](design-stage3-ai-assisted-tagging.md):

- The review panel needs prominent placement — it's a core workflow, not a settings screen.
- The "AI Review" tab badge (unreviewed count) is the primary signal that work is waiting. It should be visible without scrolling.
- Keyboard shortcuts (`A` accept, `R` reject, `E` edit) mirror the modal pattern — keep them consistent.
- The unclassified badge on the photo grid (§2) doubles as a visual prompt to switch to the AI Review tab.

If tabs aren't built before Stage 3 lands, the review panel can sit above the photo grid temporarily, but it should be first-class in the layout, not an afterthought panel.

---

## 6. Other remaining wins

- **`multiple` unit filter** — backend change needed (repeated query param). Noted in §1.
