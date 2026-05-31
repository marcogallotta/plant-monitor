# AI-Assisted Tagging — Design & Handoff

_Status: active. Last restructured 2026-05-31._

---

## How to use this doc (read first)

This is the handoff surface for any Claude picking up AI tagging. Orientation:

1. **Read "Current approach" — the authoritative, live plan**, including "Confusable rules &
   heuristics" (the classification cheat-sheet). It is what to *do today*. Where it conflicts
   with anything in the Appendix, this section wins.
2. **Verify state against the live DB.** Known plants / container bindings are in
   `growing_units` (source of truth), not prose — query `GET /assistant/growing-units` and
   reason by capture date; any plant list in this doc is a stale hint.
3. **The Appendices are evidence/bootstrap, not instructions.** Appendix A = the confirmed
   few-shot example pool (bootstrap for reference sheets; migrate to a live
   `photo_ai_suggestions` query when built). Appendix B = dated session logs (why the
   decisions were reached); don't act on a superseded log over the head.

**Source-of-truth split:** this doc = durable *mechanism + decisions + classification
cheat-sheet*. `growing_units` (DB) = live plant/container *state*. `photo_ai_suggestions`
(DB) = raw per-photo verdicts (Tier 2). _(The former `tagging-calibration.md` is merged into
this doc as of 2026-05-31.)_

---

## Current approach (authoritative)

### Goal & constraint

Triage ~1000 unclassified photos into the DB with human-in-the-loop confirmation. **Hard
constraint: the producer is a Claude Code session on a Max $100 plan** — every read burns
the user's capped allowance (not a per-token API bill). Optimise for *throughput within a
fixed budget*, not perfect classification. Do not build infrastructure before the cheap
pass is validated.

### Pipeline shape

```
prepare batch → Claude Code reads sheet(s) + emits suggestion JSON
  → ingest JSON into photo_ai_suggestions → human review → repeat
```

Claude never writes final tables. Ingest is the simplest thing that works (script or thin
endpoint — both exist; see Build status). The backend makes **no Claude API calls**.

### The unit of work is a track, not a photo

Don't classify 1000 cold photos. Classify **tracks**: a container's photos ordered over
time. One identity decision per track, and the growth trajectory both (a) resolves the
seedling/stage ambiguity that pixels and static date cannot, and (b) *is* the "how's it
doing" monitoring signal (growth rate, stress onset, recovery). Same sequence answers both
"what is it" and "how's it doing."

**Dependency — but NOT a blocker for the bulk run.** A *cross-week* track requires the
photo→container mapping threaded across time, which needs container identity — the hard,
non-persistent part (pots move; identical troughs; position ≠ identity). **Do not block the
first 1000 on solving this.** For the bulk run, simulate threading with **per-session
hints** ("herb shelf; Moroccan mint in the trough, peppermint in the pot"). Within a
session, threading is trivial (adjacent shots, same subject), so sequence + age inference
work *within* each session for free. True cross-week threading (per-session human link vs.
visual recognition) is a later problem; deferring it only defers cross-week date-inference,
not the ingest.

### Batching: time-chunked sessions, with stacked context

Group photos by **capture-time gaps** (same 10–15 min window = same session = same plants,
light, day). Feed a session together so the model cross-references — the clearest shot
anchors the ambiguous neighbours.

The priors **compound**, and this is the core insight:

- **Time-chunk** → batch shares subjects, lighting, day.
- **Date + unit timeline** → "shot May 20, unit sown Mar 1 ≈ 80 days = mature" collapses
  stage ambiguity *before* looking at a leaf. **Date is a first-class input** (derived by
  inference — see "Date is wired in by inference" below).
- **Sequence** → later identifiable frames back-propagate identity to early seedling frames.
- **Reference sheet** → anchors cross-session confusables (the two mints, etc.).
- **Within-batch anchoring** → clean neighbour pins the species for blurry ones.

**Consequence — context compensates for resolution.** When the model has session + age +
sequence + look-alike anchors, it is not guessing from leaf pixels alone, so it tolerates
*lower* per-cell resolution. That loosens batch size: bigger batches become viable because
the other (free) priors carry the load resolution used to. "Keep it to 6 cells" was a
pixels-only rule and does not bind once context is stacked.

**Pick the batch size empirically.** Bounded above by (a) output length — a turn can only
emit so many reliable JSON rows — and (b) attention decay across a long image set. Find the
sweet spot in the calibration run (try 256px sheets at 6 / 12 / 20 per batch *with* dates +
ref + session grouping on the first ~60–100 photos; scale with whatever holds accuracy).

### Resolution & model (the budget decisions)

- **One pass, 256px contact sheets, on a cheap model (Sonnet; Haiku for obvious repeats).**
- **No mass 1024px escalation pass.** 1000×1024 ≈ 1.2M image tokens (`(w*h)/750`,
  ~1,200/photo) would torch the weekly Max allowance. 256px ≈ 87 tokens/photo → ~87k for
  all 1000 (~14× cheaper). Reserve Opus, if at all, for a tiny hand-picked confusable set.
- **Gate on confusable-class membership, NOT stated confidence.** At 256px, confidence is
  *anti-calibrated* on look-alikes — in the A/B test both "high"-confidence 256px calls were
  wrong (chilli→basil, Moroccan→peppermint). "High confidence on a confusable" is a red
  flag. Auto-accept only distinctive/mature plants outside the confusable classes.
- **Confusables → fix by hand** in the review tab (a handful per batch, not 1000).
- **Seedling-stage cases → route to date/sequence**, not resolution. Resolution does not
  fix them (chilli-vs-basil seedling stayed wrong even at 1024px); the time sequence does.

### Reference sheet (cheap, keep it)

Show **one reference sheet per batch**, amortised: ~9 confirmed examples at 256px (3×3 ≈ 786
tokens) ÷ ~10 photos ≈ 79 tokens/photo. For all 1000 that's ~87k → ~166k total — trivial on
the plan. Rules:

- **Target the confusable classes only** (two mints, allium clump, parsley/cilantro,
  basil/chilli, rau ram/sorrel). A sheet of distinctive plants is wasted tokens.
- Source examples from **Appendix A** (confirmed few-shot pool).
- Show **ref sheet + batch sheet in the same turn** (Claude can't carry images across
  turns). Keep the *batch* sheet's cells legible; the ref sheet can be denser (it's an
  anchor, not judged).
- Honest limit: lifts species ID (already the strong axis). Does nothing for seedling-stage
  or zone-undercounting — those need date/sequence and region tagging respectively.

### Confusable rules & heuristics (classification cheat-sheet)

Merged from the former `tagging-calibration.md`; learned by correction. When you hit a
confusable, **emit a tight `suggested_options` set rather than committing** — the offered set
has reliably bracketed the truth (every binary held across calibration rounds). Keep
"unknown" open; never force a plausible-but-wrong pick. Disambiguate look-alikes by
**container**, not position.

| Looks like | Offer | Resolved by |
|---|---|---|
| Same-looking mint | peppermint / Moroccan mint / **spearmint** | container (peppermint=pot, Moroccan=trough); spearmint = the 3rd mint the old binary missed |
| Fine grassy allium clump | chives / Welsh onion / garlic chives | near-identical as clumps |
| Lobed apiaceae seedling | parsley / cilantro | date / sequence |
| Reddish-node stem cuttings | lemongrass / rau ram | both propagate this way |
| Broad oval-leaf seedling | basil / chilli | date-from-sowing (resolution does NOT fix it) |
| Sprawling reddish stems, poor condition | rau ram | rau ram reddens/sprawls under stress |

**Heuristics:**
- **Offer binary/n-ary options — they bracket the truth.** Recall of the offered set is the
  metric, not the model's own pick.
- **Species is the easy part.** Vision is reliable on mature/distinctive plants. The live
  failure modes are **zone undercounting** (always scan frame edges of multi-plant shots) and
  **stage/context** (seedling vs transplant vs mature) — neither fixed by looking harder; use
  date/sequence + hint.
- **Not everything is a plant.** Soil-moisture tests, repot-in-progress, process shots →
  **Delete**, don't tag.
- **Suggest rotation.** Read with stored `rotation` applied; if upright disagrees, emit
  `suggested_rotation` (auto-fix high confidence, queue the rest).

### Region-level / multi-species

One photo often holds several species arranged spatially. Tag **per region**, not per photo
(`photo_ai_suggestions` carries an optional bbox; one photo → many rows). **Zone
undercounting** (dropping secondary species at frame edges) is a persistent real miss —
always scan edges of a multi-plant shot.

### What vs. how's it doing (persistence model)

- **Container → species: persistent** until repot/resow/harvest. The durable asset is the
  `growing_unit`; register it at sowing so vision never has to ID a cotyledon.
- **Spatial layout: ephemeral** — pots move. **Do not persist layouts.** Photo→container is
  re-established per session (the threading problem above).

### No keep/discard gate (Pi only)

The Pi produces overhead balcony shots — monitoring photos by definition, so no gate. The
gate existed only for the one-off 2,626-photo phone camera-roll backfill (done). **Caveat:**
batch-tagging `manual`/`phone` source photos again reintroduces junk and needs the gate.
Even `manual` shots include the occasional non-plant test image → **Delete** is a
first-class review action.

### Date is wired in by inference, not by manual entry

Date is the **highest-leverage, near-free prior** (text, not pixels) and fixes the one
failure resolution can't (seedling-stage). But **do not require the user to record
sowing/purchase dates per unit — that's recurring work that won't get done.** Derive the
age anchor from the photo timeline itself:

- A **confidently-identified frame anchors the age** of the whole track. A clearly-readable
  Thai basil seedling in early April establishes "this container was ~a seedling then," which
  implies sown ~X weeks prior and dates the rest of the track.
- That anchor **propagates along the time-ordered photos** (capture dates are known): earlier
  ambiguous frames are "younger than the anchor," later ones "older," so each ambiguous frame
  inherits an expected stage and the seedling guesswork collapses.
- The clear frames don't have to be the seedling ones — a confident *mature* ID also dates
  the track backwards ("obvious mature basil in June ⇒ the April seedling frames in this
  track were that basil").

So the model reconstructs the timeline from the few most-identifiable frames rather than
from a hand-maintained date field. Manual `started_at`/event dates remain an *optional*
refinement when known, never a prerequisite.

**What this needs:** photos ordered by `captured_at` within a track. *Within a session*
that's free (no threading needed), so age inference works on the bulk run today. *Cross-week*
inference waits on container threading — deferred, not blocking. No new mandatory schema.

### Rollout plan (calibrate, then scale)

Don't run 1000 at once; find the batch size empirically, then scale.

- **A. Choice flow** — `suggested_options` is built (migration 0011). Outstanding: the
  open-ended-question fallback (free-text answer when no option set fits).
- **B. Minimal `scripts/prepare_tagging_run.py`** (the calibration instrument): query
  unclassified photos sorted by `captured_at`; group into sessions by capture-time gap
  (default 15 min); batch at configurable size; call `GET /assistant/contact-sheet` per
  batch; optionally attach a confusable reference sheet; write
  `data/tagging-runs/<run_id>/manifest.json` + one prompt `.md` per batch. **No Claude API,
  no ingest.** Keep it thin — don't gold-plate manifest infra before the format is proven.
  Manifest = restartability (status per batch: `prepared|ingested|reviewed`); without it
  1000 photos becomes mud.
- **C. Calibration run, ~60–100 photos, three formats: 6 / 12 / 20 photos per 256px sheet**,
  same prompt + reference context. Measure per format: review time/photo, delete rate, edit
  rate, wrong-option rate, missed-secondary-species rate.
- **D. Pick the winning batch size.** Criterion: **lowest review time/photo at an acceptable
  correction rate.** Reject any size where missed-secondary-species or wrong-option rate
  visibly rises — throughput from bigger batches is worthless if it leaks errors into the
  accepted set.
- **E. Run ~200** → review → adjust prompt.
- **F. Run the remaining ~700–800.**

---

## DB schema

```sql
CREATE TABLE photo_ai_suggestions (
    id SERIAL PRIMARY KEY,
    photo_id INTEGER NOT NULL REFERENCES photos(id),
    model VARCHAR(100) NOT NULL,
    batch_hint TEXT,
    prompt_context JSONB,          -- temporal neighbours, known plants sent
    -- one row PER REGION, not per photo: a multi-plant photo yields several rows.
    x REAL, y REAL, x2 REAL, y2 REAL,   -- normalised bbox of the region (NULL = whole photo)
    suggested_plant_id INTEGER REFERENCES growing_units(id),  -- usually NULL at cold start
    suggested_plant_name TEXT,     -- free text; the primary species output until units exist
    suggested_photo_type TEXT,
    suggested_rotation INTEGER,    -- 0/90/180/270 if upright orientation disagrees with stored
    suggested_labels JSONB,        -- list of label strings
    suggested_options JSONB,       -- candidate names for confusables (migration 0011)
    confidence TEXT,               -- high / medium / low
    question TEXT,                 -- populated when confidence is low
    observation TEXT,              -- one-sentence visual note
    status TEXT NOT NULL DEFAULT 'pending',  -- pending / accepted / edited / rejected / deleted
    edited_plant_id INTEGER REFERENCES growing_units(id),
    edited_photo_type TEXT,
    edited_labels JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);
```

- `suggested_plant_id` usually NULL at cold start; the real output is free-text
  `suggested_plant_name`. Accepting can *create* a `growing_unit`.
- Region-level: `x/y/x2/y2` reuse the note-rectangle convention. NULL bbox = whole photo.
- `status = 'deleted'` records a decision to bin the underlying photo (test/process shots).
- `edited_*` hold the human's corrections on "Edit".

## Claude's structured response

```json
{
  "suggested_plant_id": 12,
  "suggested_plant_name": "Sorrel",
  "confidence": "high",
  "suggested_photo_type": "health_check",
  "suggested_labels": ["delivery_stress", "wilting"],
  "suggested_options": ["Rau ram", "Sorrel"],
  "suggested_rotation": null,
  "question": null,
  "observation": "Dramatically drooping over pot sides, reddish stems — transplant shock."
}
```

For confusables, prefer `suggested_options` (a tight candidate set) over a confident single
guess — recall of the offered set is the metric that matters, and the offered set has
reliably bracketed the truth. When `confidence` is `low` and no clean option set fits,
populate `question`.

## Surfaces (transport-agnostic)

Operations the review UI needs against `photo_ai_suggestions`:

- **Ingest** a batch of suggestion rows (produced by a Claude Code session).
- **List** pending suggestions with photos/regions.
- **Resolve**: accept / edit / reject / delete. Accept writes through to
  `photos.photo_type`, `photos.rotation`, `photo_growing_units`, `photo_labels` (may create
  a `growing_unit`/label) in one transaction; delete bins the underlying photo.

## Build status

**Tagging — done:**
1. ✅ `photo_ai_suggestions` table + migration (region fields, `suggested_rotation`,
   nullable `suggested_plant_id`, `deleted` status).
2. ✅ Ingest path — `scripts/ingest_suggestions.py` + `POST /suggestions/ingest`.
3. ✅ `GET /suggestions` — list pending with photo metadata + region coords.
4. ✅ `PATCH /suggestions/{id}` — accept / reject / deleted; accept writes through and
   creates a `growing_unit`/`label` if needed.
5. ✅ Review tab — region overlays, keyboard nav (A/R/D/J/K), shortcut hints, click
   thumbnail → full modal.
6. ✅ Action buttons on every card.
7. ✅ Inline edit form — plant name (datalist autocomplete), type picker, labels.
   Overrides → `edited_*` + `status='edited'`; no overrides → `status='accepted'`.
   Case-insensitive unit lookup.
8. ✅ `suggested_options` (migration 0011) — choice buttons for ambiguous cases.

**Tagging — outstanding:**
- **Date-by-inference**: feed time-ordered track photos so a confidently-identified frame
  anchors the track's age and propagates to ambiguous frames (no manual date entry). *Top
  priority — see "Date is wired in by inference" above.* Depends on track threading.
- **Track/sequence tagging** + the photo→container threading it depends on.
- **`scripts/prepare_tagging_run.py`** — the calibration instrument (see Rollout plan B).
  Build it *thin* for the calibration run; expand manifest infra only once the format proves
  out.
- **Session-propagation review actions** — "same plant/type as previous", "apply this plant
  to selected pending". **Human-triggered only** — never auto, since a near-duplicate may be
  a different pot. Likely the single biggest throughput win, more than a smarter model.
- **Run provenance (before scaling past calibration, not before it)** — add `run_id` +
  `batch_id` to `photo_ai_suggestions` (or at minimum store them inside the existing
  `prompt_context` JSONB) so a bad suggestion is traceable to the run that produced it.
  Columns are cleaner before the 1000-photo run; `prompt_context` is enough for calibration.
- **Duplicate-ingest protection** — accidental re-ingest will happen at scale. Skip on
  `(run_id, photo_id, bbox, plant/options)` match. Not perfect dedupe — just enough to keep
  duplicates out of the review queue.
- **Open-ended question fallback** — when `question` is set but `suggested_options` is empty,
  there's no free-text answer input yet.
- **Enlarge / focused review mode** — future; clicking a thumbnail currently opens the modal.

---

## Capture queue (deferred — reference only)

> **Scope:** pre-Pi guesses. Do not build the gap rules until real Pi capture behaviour
> exists. Kept as reference, not a commitment. At most, stub the `capture_requests` table +
> a trivial list/resolve surface if something needs to write to it.

The Pi auto-captures overviews; the system tells it what to shoot next. Gap-detection rules
evaluate DB state to produce capture requests.

| Rule | Trigger | Suggested shot |
|---|---|---|
| Stress label, no follow-up | `wilting`/`sulking`/`delivery_stress`, no photo in 3 days | `health_check` |
| Incident, no resolution | `aphids`/`pest_damage`, no follow-up | `closeup` |
| No photo in 7+ days | unit has no photo this week | `overview` |
| Unregistered plant visible | `multi_plant`, no plant association | per-pot `overview` |
| Post-repot gap | `root_bound`, no photo since event | `health_check` |
| New purchase, no follow-up | `new_purchase`/`delivery_stress`, no photo 48h later | `health_check` |

```sql
CREATE TABLE capture_requests (
    id SERIAL PRIMARY KEY,
    growing_unit_id INTEGER REFERENCES growing_units(id),
    plant_name TEXT,
    suggested_shot_type TEXT NOT NULL,  -- overview / closeup / health_check
    reason TEXT NOT NULL,
    priority INTEGER DEFAULT 2,         -- 1=urgent, 2=normal, 3=low
    source_photo_id INTEGER REFERENCES photos(id),
    status TEXT NOT NULL DEFAULT 'open',  -- open / captured / dismissed
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
```

```
GET   /assistant/capture-queue         → open requests by priority
PATCH /assistant/capture-queue/{id}    → captured | dismissed
```

---

## Open questions

- Container threading (cross-week): per-session human link, visual recognition, or something
  else? Deferred — the bulk run simulates it with per-session hints; this only gates
  cross-week date-inference, not ingest.
- Auto-generate `capture_requests` on a schedule, or manually after each import batch?
- Mobile-friendly review UI for quick phone yes/no, or desktop-only for now?

---

## Appendix A — confirmed few-shot example pool

Ground-truthed by the human across calibration rounds (2026-05-30). Re-read these thumbnails
as visual priors when tagging the matching species; they are the source for the per-batch
**reference sheet** (confusables only). Filenames under `data/photos/`. **Bootstrap** — when
a live `photo_ai_suggestions` query is built (pull accepted/edited examples per species),
retire this static list. Verify against the DB; pots move and plants die.

**Single / dominant subject:**
- `554b3a646dc64b3399b6382c3c81ce68.jpg` — dill, mature, leggy/floppy
- `291ff4b9585540eab4f55c00347d02ca.jpg` — Thai basil, seedlings
- `457790d2c20d4d2090dbf1a87242dcf0.jpg` — genovese basil, seedling
- `c9860a82b9594b83a0f0c1658becc874.jpg` — genovese basil, young plant
- `b2d470329a6f43c9b3f78bd3a5e47837.jpg` — chilli, seedling (guessed basil-or-chilli; chilli)
- `892b874e1bac4f25821c8f744ee3dd9e.jpg` — chives clump (allium binary; chives)
- `19af7b97567d47f8bf32f2a57db45334.jpg` — peppermint, fresh water→soil propagation, stressed (misread as seedlings — stage error)
- `7236f3ff21474d17be7ab0e287f728a5.jpg` — rau ram, sprawling/stressed
- `db60aae6b3e6418f99c107c3bf2bc039.jpg` — rau ram, severely wilted (moved indoors)
- `7faf996c30144613a03c21aad20830ee.jpg` — lemongrass cuttings, new nursery purchase

**Multi-species (region-tagged):**
- `000cf7f3d4f64299b2d3dd454fd06eab.jpg` — peppermint (top-right pot), fenugreek (top-left trough), rocket (left third middle trough) + cilantro (right 2/3), parsley (middle third bottom trough) + dill (right)
- `ac85543fb0e442549ef03b2f6e56d3ff.jpg` — sage (top-left pot), parsley + dill (right), rocket + cilantro (middle)
- `d630dda5ddf643f2bc4ff61df40cefa7.jpg` — parsley (top 6 cells) + genovese basil (bottom 6)
- `09923168f26e487992fa7c65a9a1237c.jpg` — Moroccan mint (trough), genovese basil (below), Thai basil (bottom-left), Welsh onion (above), rocket (top-right)
- `5e43054b5eb545658514a1681c88a1d9.jpg` — lemongrass, rosemary, sage, peppermint, genovese basil (dense pot), sorrel (leaf, bottom-right), parsley, chives
- `9b523deb3f3b46db9ecbb8b25916e713.jpg` — parsley / cilantro seedlings (6-cell tray)
- `f6304791e4a64bf18f19172622ec836f.jpg` — Thai basil + genovese basil (one trough)

**Discard (not monitoring photos):**
- `34af94c1ded745ee95828eb2a2d41062.jpg` — soil-moisture test close-up → delete

_Scoreboard: 18 photos over 3 rounds — every confusable binary held; misses were zone
undercounting and stage/context (propagation transplant read as seedling)._

---

## Appendix B — session findings (evidence log, chronological)

Dated records of how the decisions above were reached. **Evidence, not instructions** —
where these conflict with "Current approach", the head wins. Earlier prose in this log that
the head supersedes (e.g. the original per-photo flow, the keep/discard gate for Pi, the
server-side Claude-API endpoint) is retained only for context.

### 2026-05-29 — original draft, trial run, and bulk backfill

**Trial-run lessons (human-Claude loop):** timestamp proximity is a strong signal (±60s ≈
same subject; same 10-min window ≈ same session); targeted prompts beat generic; delivery-day
context unlocks plant association; variety info is invisible from photos alone.

**Bulk backfill (~2,626-photo phone roll → 891 keepers):** a cheap binary keep/discard gate
(25-per-5×5 contact sheet, "is this a monitoring photo of my plant?") ran *before* per-photo
tagging. Keep only if an actual living plant of the user's own is in frame. False-keep ≈30%
before the rule tightened; an aggressive auto-discard then hit ≈8% false-reject — so an
automated gate should bias toward keep on ambiguous soil/tray shots. Confusables at 160px:
grains/flour vs soil, sparse seedling tray vs bare soil, harvested-on-board vs growing-in-pot,
sprouting scraps vs propagation, jars of liquid. _(Superseded for the Pi pipeline by the
2026-05-30 "no gate" decision; still applies to any manual/phone re-tag.)_

The original draft also specified a per-photo flow, batch hints, temporal context (±5 min
neighbours, known units, existing labels), and a server-side `/assistant/ai-suggestions/batch`
endpoint that *ran* Claude. The endpoint is **cut** (see 2026-05-30 decision 2).

**Batch hints** remain valid and load-bearing: per-group hint (not per-photo or per-batch),
stored per suggestion row for audit. Examples: "delivery day — probably rau ram and sorrel",
"repotting session — expect root balls", "check for stress — away a week".

### 2026-05-30 — decisions & calibration

**Decisions:** (1) **No keep/discard gate** for the Pi pipeline (overhead monitoring shots
only); still needed if re-tagging manual/phone. (2) **Claude Code is the producer, never the
Anthropic API** — backend serves lists + ingests JSON; no key, no SDK, no per-call cost.
(3) **Cold start is vocabulary-building, not accuracy** — first batches teach the taxonomy;
`suggested_plant_name` (free text) carries it until units exist. (4) **Batch hints are
per-group.**

**Findings (two 6-photo samples, full-res off disk):** known-list value is real but bounded
— confirms mature/distinctive plants, turns confusables into a binary that held the truth,
does nothing for early seedlings. **One photo contains multiple species arranged spatially →
tag per region.** Context (new purchase) is unrecoverable from pixels → validates hints.
**Date is a growth signal** — capture date + sowing date = age = expected stage, cutting both
the species (seedling disambiguation) and condition (actual vs expected stage) axes.
Confusable-binary mechanism validated (offered set bracketed truth repeatedly); container
shape carries species (peppermint=pot, Moroccan mint=trough); **Delete must be a first-class
review action**; zone undercounting is the consistent miss. **Rotation** can be emitted as a
suggestion. Two-tier memory: Tier 1 = distilled
cheat-sheet (now merged into this doc's head + Appendix A); Tier 2 = `photo_ai_suggestions`
(raw verdicts, few-shot + confidence calibration). Reframe:
"what" (persistent per container, ephemeral per position) vs "how's it doing" (dynamic).

### 2026-05-31 — first live ingest run (42 suggestions, 7×6)

**Worked:** contact-sheet endpoint (`GET /assistant/contact-sheet?ids=…`) is the right
primitive; 256px 3×2 is the species sweet spot (above 3×3 per-cell resolution hurts);
`suggested_options` choice buttons resolve confusables fast; vocabulary grows fast (8 new
units in one session); ingest + DB-reset workflow is practical.

**Did not work — prior wiring:** "priors active" batches were **not better than cold-start**.
Root cause: the richer unit *name* list was passed, but **no confirmed photo thumbnails were
shown as visual anchors**. Claude can't carry images across turns → visual priors must be a
**reference sheet shown in the same turn** as the new batch. Until built, every batch is
effectively cold-start on species ID. _(Now resolved in the head: amortised per-batch ref
sheet targeting confusables.)_

### 2026-05-31 — resolution A/B test & token-budget decision

Blind A/B (fresh readers, no calibration doc, same known-plant list, 6 known-failure photos):
**256px contact-sheet vs ~1024px individual.**

- Set-recall (offered set contains truth): **256px 3/6 → 1024px 5/6.** Correct top pick
  0/6 → 2/6. Full-res *flipped two confidently-wrong 256px calls* (peppermint→Moroccan,
  cilantro→parsley).
- **256px stated confidence is anti-calibrated on confusables:** both "high"-confidence 256px
  calls were WRONG (chilli→basil, Moroccan→peppermint). → gate on confusable-class membership,
  not confidence.
- **One failure survived even at 1024px (chilli vs basil seedling).** Seedling-stage
  confusables don't resolve at any resolution — only date/sequence fixes them.

**Token math:** ~1,200 tokens/photo at 1024 (`(w*h)/750`) → ~1.2M for 1000. 256px ≈ 87/photo
→ ~87k for 1000 (~14× cheaper). **Decision (Max $100):** producer is a Claude Code session →
this burns the capped allowance, not a $ bill. One 256px pass on a cheap model; no mass 1024
escalation; fix confusables by hand; date/sequence for seedlings. _(Folded into the head.)_

### 2026-05-31 — design discussion (folded into head)

Stacked-context batching (session grouping + date + sequence + ref sheet + within-batch
anchoring; context compensates for resolution → bigger batches viable, size found
empirically). **Tag tracks, not photos** — growth sequence resolves seedlings and doubles as
the health axis; depends on photo→container threading. Per-batch ref sheet is cheap enough to
keep. Date is the unused, near-free, highest-leverage prior and is **not yet wired** — top
priority (later reframed as inference-from-timeline within a track, needing no mandatory
schema; see head).
