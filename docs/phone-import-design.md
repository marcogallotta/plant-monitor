# Phone Import & Triage — Design Doc

_Date: 2026-05-30_
_Status: Draft — revised after local-heuristic feasibility test_

---

## Context

Phone photos currently upload via a browser file picker that requires manual selection. Two problems:

1. Selecting ~90 photos manually is painful.
2. Android Chrome's `File` objects go stale after the page has been open too long, causing silent upload failures.

This doc covers a redesigned phone import flow. It originally also proposed an AI triage pass to auto-discard non-plant / blurry / dark photos. **That auto-discard idea was tested against real data and does not work locally** — see "Feasibility test" below. The design is now split:

- **v1 — local selection ergonomics.** Make selecting easy. No auto-hiding, no AI, nothing leaves the device. Ships first.
- **v2 — model-based triage (optional, later).** A vision model makes the keep/reject call that cheap pixel stats provably cannot.

---

## Feasibility test (2026-05-30)

Before building, we tested whether cheap, local image statistics could separate "keep" (my plant) from "reject" (junk) on real phone photos. Scored every image at 128px (the size the browser would compute on load): **ExG green fraction**, **mean luminance**, **saturation**, **Laplacian blur**, and **EXIF camera-tag presence**. Method/script was a throwaway (`/tmp/triage_test.py`).

### Data

- 147 existing curated photos in `data/photos` (all keepers).
- 10 raw phone uploads: 9 plants (several wilted/dying, two shot at night at luma ~28, one held in hand) + 1 selfie.
- 12 deliberately-seeded non-keepers: legs/shoes on the floor, a dumbbell, a Neem-oil bottle, pesto in a dish, supermarket flour/olive-oil shelves, an olive-oil nutrition label, broccoli (in-hand, close-up, and in the store bin).

### Results

| signal | what it does | verdict |
|---|---|---|
| green fraction (ExG) | measures chlorophyll | **useless as keep/reject** — distributions overlap |
| luminance | brightness | only catches dark; real plant photos are legitimately dark |
| blur (Laplacian) | sharpness | unreliable at 128px; darkness flattens it; Brave's canvas farbling inflates it |
| EXIF camera tags | photo vs screenshot | catches screenshots only; muddied by re-encoding on stored files |

**The killer finding:** green fraction does not separate keepers from junk because *the junk is also full of vegetation*. Concrete overlap from the test set:

- Broccoli at the supermarket: **48% green**. Pesto in a bowl: **21%**.
- Real keepers: wilted plants **6–10%**, dark night basil **40–45%**, seedlings in white hydroponic towers **<5%**.

So broccoli and pesto outrank several genuine plant photos. No green threshold can split "my basil in a pot" from "broccoli in a shop" — both are chlorophyll. The same collapse happens on every other cheap axis: the lone selfie (0% green, skin tone, low texture) sits in the exact same feature-space region as dying plants and hand-held shots.

### Conclusion

The decision that actually matters is **"is this my plant, in situ"** vs **"vegetation somewhere else"** (a shop, a bag, a bowl, a label). That is a *semantic / scene-context* judgement — held-in-hand + plastic bag = shopping; shelves + price tags = store; bowl + utensil = food; pot/soil/balcony = my plant. **No local pixel statistic captures it.** Auto-discard based on local heuristics would wrongly hide dying/dark/seedling plants (the most valuable shots) while keeping groceries.

Therefore: **v1 does no automatic keep/reject.** Local stats are used only to *order* the grid, never to hide. Real quality filtering needs a model (v2).

### Performance (measured)

Decode + downsample to 128px: **~23 ms median, ~45 ms p90** on server CPU (phone differs, but the pipeline is light). Cost is dominated by JPEG decode of the ~12 MP source, not the target size or the metric math. In-browser scoring is cheap enough — it just isn't *useful enough* to gate on.

---

## Photo source & status

### `source`

Phone uploads are tagged `source: phone` (already wired through `buildUploadFormData` → `/manual-photos`). This distinguishes them from `manual`, `sd`, and Pi uploads.

### `status` (deferred to v2)

The original four-state `status` column (`active` / `pending_triage` / `needs_review` / `discarded`) existed to support auto-triage. **v1 does not need it** — every imported photo is just `active`, exactly like manual/SD uploads today. The column lands with v2 when there's an automated decision to record. v1 ships with no schema change.

---

## v1 — Phone import flow (local, ships first)

### Goal

Make selecting easy and kill the stale-`File` bug. No AI, no upload to anyone, no auto-hiding.

### Behaviour

1. User taps **Import from phone** in the Import tab.
2. File picker opens (`accept="image/*"`, `multiple`). User selects from the gallery (Android: long-press → Select all for a bulk grab).
3. A grid renders thumbnails. **Each file is decoded once at 128px on load** — that single decode produces the thumbnail, the lightweight score, *and* the uploadable Blob copy (see "Stale-`File` safety"). Piggyback, don't decode twice.
4. **Default selection state: all selected.** Normal phone plant sessions are mostly keepers, so deselecting a few duds is less work than tapping every keeper. Quick controls: **Select all / Select none / Invert**.
5. Grid is **sorted newest-first by default** (matches the SD-import convention and user intent: you just shot these). A non-default **"suggested order"** toggle re-sorts by the green score so obvious non-plants (legs, shelves, labels) cluster lower — but this is a *soft hint only*, never a filter, and is explicitly not called "plant-likelihood" because the feasibility test showed green pushes dark basil and seedlings down while floating broccoli up.
6. Selected photos upload sequentially via the existing `/manual-photos` path, each tagged `source: phone`. Progress bar: `Uploading n / N…`.

### Why a grid (reversing the earlier "no grid" decision)

The original doc removed the grid for phone mode to dodge the stale-`File` bug. But selection ergonomics *need* a grid. The stale-`File` bug is avoided differently and correctly: **read each file's bytes promptly on load** (decode to the 128px thumbnail/score, keep the resulting Blob), rather than holding raw `File` handles open until the user finally hits import. Once decoded, the original handle going stale doesn't matter.

### Stale-`File` safety

The concrete per-file lifecycle, on load — **two separate captures, do not conflate them**:

```
File → (a) read original bytes promptly → upload Blob (full/near-full quality)
     → (b) decode once to 128px → thumbnail object URL + lightweight score
     → drop the original File reference
```

Upload sends **(a), the original-byte Blob — never the 128px re-encode from (b), and never the original `File`.** The 128px decode is for display and scoring only; uploading it would silently destroy archive quality. Once both captures exist, the original handle going stale is irrelevant.

**Memory discipline (matters for 240-photo bulk):** do **not** retain full-resolution decoded bitmaps. Per entry keep only: the upload Blob (a), the thumbnail object URL (b), and the small score.

- Close each `ImageBitmap` immediately after drawing to the scoring canvas.
- Bound decode concurrency to ~3–4 `createImageBitmap` calls in flight (a 12 MP bitmap is ~48 MB; never hold hundreds at once).
- **Chunk the whole import into batches of 20–40 entries**, not just bounded decode concurrency: even the upload Blobs add up (240 × ~3 MB ≈ 700 MB resident). Capture, render, and upload a batch before materializing the next. Bounded concurrency limits *decode* spikes; chunking limits *total* resident bytes.
- Revoke thumbnail object URLs after upload completes or when the grid is cleared (the existing SD flow already does this via `URL.revokeObjectURL`).

**Upload-Blob quality:** the simplest correct path is to upload the **original file bytes unchanged** (capture (a) is just the raw bytes). Only re-encode if you deliberately want to cap archive size (e.g. a sane max edge for huge originals) — and if so, re-encode from a *full-resolution* decode, never from the 128px scoring decode.

### Duplicate detection (re-import safety)

A bulk import can be interrupted (page closed, connection drop) and re-run. Already-uploaded photos must not duplicate. Current server-side dedup keys on `original_filename + original_size_bytes` (see `internals.md`), which is weak for phone photos: Android content providers hand out generic names (`image.jpg`) and unreliable sizes, so it both false-positives (size collision → wrongly skipped) and false-misses (re-encoded/renamed → re-uploaded).

- **Ideal:** content hash (SHA-256 of the uploaded bytes), enforced server-side. But a `sha256` column is a **schema change**, which v1 explicitly avoids — so true hash-dedup belongs with the v2 migration, not v1.
- **v1 stance:** keep the existing filename+size soft-check (no worse than today), and **rely on the grid for the real safety net** — the user sees what's selected and can deselect. Do not claim "safe re-import" in the UI beyond what filename+size actually guarantees.
- When the v2 migration lands, add `sha256` and switch dedup to hash. Note it here so it isn't forgotten.

### Brave note

Brave is Chromium, so decode speed matches Chrome. Default Shields *farble* `getImageData` with per-pixel noise: green/luma averages are unaffected (noise washes out over thousands of pixels), EXIF is untouched (read from file bytes, not canvas), but **blur (Laplacian) is corrupted** — another reason blur is not used in v1. On the user's own self-hosted domain, Shields can be lowered if exact pixels are ever needed.

---

## v2 — Model-based triage (optional, later)

Only the semantic "is this my plant in situ" call needs a model. Two implementations, both pluggable behind the same UI:

| Option | Privacy | Accuracy | Cost |
|---|---|---|---|
| **Claude vision** | images leave the network to Anthropic's API (commercial terms: not used for training, limited retention) | **proven** — 22/22 on the spike set; reads scene context (shelves, packaging, food) | a few cents per 100 photos at Haiku-class; ~0.3 MB total at 256px for 100 photos |
| **Local classifier** | nothing leaves the box | needs a plant/scene model + setup | one-time, free per-run |

### If Claude

- Runs **server-side** (never expose the API key in the browser); endpoint behind the same dashboard Basic Auth as everything else.
- **Async job**, not a blocking request: `POST /triage/run` enqueues and returns a `job_id`; `GET /triage/status/{job_id}` returns `{processed, total, summary}`. A 240-photo run is minutes of work — a single synchronous request would hit Funnel/proxy timeouts and can't drive a progress bar.
- Send a **small** image. The spike below showed scene-context cues (packaging, shelves, price tags, pots) survive aggressive downscaling — keep/reject was correct even at 128px. **256px is sufficient**, so reuse the existing 256×256 thumbnail endpoint (assistant API, see `internals.md`) — ~90 tokens/photo, fractions of a cent per 100. Higher resolution is only needed for finer tasks (leaf-health, pest spotting), not for "my plant vs not."
- Failed/incomplete photos stay `pending_triage` so re-running resumes naturally.
- Parse robustly: lowercase, strip punctuation, default to the safe bucket on an unparseable response — never silently drop.

### Status model (lands with v2)

- Add `status` (`active` / `pending_triage` / `needs_review` / `discarded`) + triage metadata (`triage_decision`, `triage_reason`, `triage_model`, `triaged_at`), all nullable, backfill existing → `active`.
- `discard` → `discarded` (hidden from gallery, never deleted); `unsure` → `needs_review` (also excluded from the default gallery, surfaced in a small review queue); `keep` → `active`.
- `GET /photos` default-excludes `discarded`, `pending_triage`, and `needs_review`. `PATCH /photos/{id}/status` for triage + manual restore.

### Feasibility spike (result, 2026-05-30)

Ran the 22-photo set (9 plants / 13 junk) through a large vision model at 512px, then re-checked the hardest cases at 128px.

- **512px: 22/22 correct. 128px: 22/22 correct** on the cases tested.
- Every case that destroyed the local heuristic was classified correctly: **broccoli ×3, pesto, mint-in-bag** (all high-green) → rejected; the model reads "plastic packaging," "price tags," "supermarket shelf," "glass dish." **Dark night basil ×2** (luma 28) and **wilted/dying plants ×3** (low-green) → kept. Selfie, legs, Neem bottle, olive-oil label, oil shelves → rejected.
- **Resolution barely matters for this decision.** Scene-context cues are low-frequency and survive to 128px (the plastic sheen, shelves, and price tags are still legible). This is why 256px is the recommended triage size above.

**Caveats:** this was a large model at high effort — the *accuracy ceiling*, not a `haiku-4-5` guarantee. Sample is small (n=22, one true selfie). The cues are obvious, so Haiku is likely strong here, but **confirm with `haiku-4-5` before production**.

**Verdict: v2 is technically viable.** The semantic model does cleanly what local pixel stats provably cannot. Build it *if and when* manual triage in v1 proves too much (the user's gate) — the technical risk is retired.

---

## Build order

### v1 — implementation phases (local, no schema change)

Each phase is independently shippable and leaves the app working. The ordering front-loads the thing that actually fixes the reported bug (stale `File`) and defers the nice-to-haves (scoring/ordering) to last, so the heuristic work — which the feasibility test showed is low-value — can be dropped or deferred without blocking the fix.

**Phase 0 — Confirm the seam (no UI change).** ✅ _Done 2026-05-30_
Verified `/manual-photos` accepts and persists `source: phone` end-to-end. Added `test_manual_upload_sets_source_phone` in `test_manual_photos.py`.

**Phase 1 — Grid with immediate byte capture (the actual bug fix).** ✅ _Done 2026-05-30_
Implemented in `sdImport.js`. `handlePhoneFilesSelected` reads ALL selected files' bytes into upload Blobs immediately with bounded concurrency (`PHONE_CONCURRENCY = 4`) via `_processPhoneBatch`; `phoneAllFiles` is cleared after processing so no `File` handles are retained. No file count cap — 97 or 240 photos work in one selection. For each file: bytes captured as upload Blob (a), decoded once to 128px via `createImageBitmap` with `imageOrientation: 'from-image'` for EXIF orientation (b), rendered to JPEG via `_bitmapToJpegBlob` (OffscreenCanvas with regular canvas fallback), EXIF parsed from the same blob. Filter is JPEG-only by name or MIME (`isPhoneJpeg`). Per-photo `readStatus: 'queued' → 'ready' | 'failed'` overlays. `sdUpdateCount` shows ready count for phone mode and disables import button while processing. Upload filters to `readStatus === 'ready'` only; `entry.uploadBlob = null` frees the full-res bytes after each upload. For bulk imports >30, the user repeats the flow.

**Phase 2 — Selection ergonomics + sequential upload.**
Add Select all / none / Invert controls and the progress bar (`Uploading n / N…`, per-thumb done/failed overlays, reusing the SD flow's pattern). Sequential upload of selected via `/manual-photos`, each tagged `source: phone`. Keep the existing filename+size dedup soft-check; do not over-promise "safe re-import" in copy. After this phase v1 is functionally complete for daily use.

**Phase 3 — Scoring & suggested order (optional, low priority).**
Compute the green/luma score from the *same* Phase-1 decode (piggyback, no second decode). Default sort newest-first; add a non-default "suggested order" toggle that sorts by green. This is pure polish — the feasibility test showed the score is weak — so it can ship later or be cut entirely without affecting Phases 0–2.

**Phase 4 — Docs.**
Update `internals.md` (phone grid flow, `source: phone`, byte-capture lifecycle). Run `make test` + `make test-e2e`.

> **Gate checkpoint:** after Phases 1–2 are in real use, observe how much manual deselection a normal import actually costs. That answer — not a guess — decides whether v2 is worth building. Phase 3's score is also the cheapest place to *measure* keep/reject effort if you want a number (see "How v1 informs v2", if added).

### v2 — model-based triage (optional, later — gated on the checkpoint above)

1. ~~Accuracy spike~~ — done (22/22 at 512px; see "Feasibility spike"). Confirm `haiku-4-5` specifically before production.
2. Migration: `status` + triage metadata (+ `sha256` for hash dedup); `GET /photos` filter; `PATCH /photos/{id}/status`.
3. Async triage job: `POST /triage/run` + `GET /triage/status/{job_id}`, server-side, behind Basic Auth, on 256px thumbnails.
4. Triage UI: trigger, progress, `needs_review` queue.

---

## Resolved decisions

- **Auto-discard via local heuristics is dropped** — empirically proven unworkable (green/luma/blur/EXIF all overlap between keepers and junk; junk is full of vegetation). Local stats are ranking-only in v1.
- **v1 ships with no schema change** — every phone photo is `active`, like manual/SD today. `status` machinery moves to v2.
- **The grid returns for phone mode**; the stale-`File` bug is handled by decode-on-load, not by removing the grid.
- **Triage, if built, is server-side, async, behind Basic Auth, on 256px thumbnails**. The accuracy spike passed (22/22; see "Feasibility spike"), so v2 is now gated only on v1 showing manual triage is too much — not on technical feasibility.
- Blur is not used as a signal in v1 (unreliable at 128px, broken by Brave farbling, confounded by darkness).
- **Default selection is all-selected, sorted newest-first** (deselect the few duds; tapping every keeper is slower). Green ordering is an optional "suggested order" toggle, never the default and never a filter.
- **v1 keeps the existing filename+size dedup** for *enforcement*; true server-side hash dedup needs a `sha256` column and is deferred to the v2 migration. But v1 **may compute** SHA-256 client-side from the upload bytes (a) to *display* likely duplicates as a hint — computing the hash needs no schema, only enforcing it does.

## Open questions

1. **Does manual triage in v1 actually prove too much?** This is now the *only* gate on v2 (technical feasibility is settled — spike passed 22/22). Decide from real v1 use: if deselecting duds in the grid is quick, v2 is never needed. If it's a slog, build v2.
2. **`haiku-4-5` confirmation:** the spike measured the accuracy ceiling, not the cheap production model. Quick re-run on the same 22 before shipping v2.
