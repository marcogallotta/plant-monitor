# AI-Assisted Tagging & Capture Queue — Design Doc

_Date: 2026-05-29_
_Status: Draft_

---

## Context

This doc covers two sequential features:

1. **Claude-assisted tagging**: unclassified photos → Claude suggestions → human review → DB write. Build now.
2. **Capture queue**: gap detection → "what to photograph next" → Pi acts on it. Build before Pi arrives (Pi Zero 2W arriving Mon/Tue).

Both live in the web UI. Neither writes final data without human confirmation.

Note: `growing_units`, `photo_labels`, and `photo_type` are already in the DB.

---

## What the trial run taught us

Before describing the design, here's what the human-Claude tagging loop looked like in practice (May 2026 session):

| Photo | Claude's read | Reality | Why it failed |
|---|---|---|---|
| Lemongrass (ID 5) | Garlic chives | Lemongrass | Visually similar at this angle. Species ID needs known-plant list + close-up |
| Dill pre-aphid (ID 67) | Healthy dill on counter | Floppy dill, early aphid stress | No targeted "is it drooping?" prompt. Generic description missed it |
| Garlic chives bundle (ID 69) | Harvested leaves | New plant arrival | No context that this was delivery day |
| Thyme in flower (ID 4) | Thyme | Lemon thyme, stress-flowering | Variety and stress history both invisible without metadata |

**Key lessons:**

- **Timestamp proximity is a strong signal.** Photos taken within 60 seconds of each other are almost certainly the same subject or event. Photos from the same 10-minute window are the same session. This should influence how the batch is assembled and what context Claude receives.
- **Targeted prompts beat generic ones.** "Is the plant standing upright or drooping?" catches floppy-dill stress. "Look for insect clusters on stems" catches aphids. A generic prompt would not have flagged either.
- **Delivery-day context unlocks plant association.** If the batch hint says "new deliveries", a bundle of leaves reads as new_purchase, not harvest.
- **Variety information is invisible from photos alone.** Lemon thyme vs. thyme, peppermint vs. spearmint — Claude cannot distinguish these without being told the known plant list including varieties.

---

## What the bulk backfill taught us (≈2,600-photo triage, May 2026)

A one-off backfill of the phone camera roll (2,626 JPEGs) was triaged into the DB. Method: downscale to 160px thumbnails, pack 25 per 5×5 **contact sheet**, and have Claude judge whole sheets at once for a binary **keep / discard** ("is this a monitoring photo of one of my plants?"). This is the cheap **pre-filter gate** that should run _before_ the per-photo species/condition tagging described below. Result: 2,626 → 891 phone keepers (956 total with manual/sd).

**This is a separate, earlier stage than the tagging loop above.** Tagging assumes the photo is already a legitimate plant photo. The backfill showed that assumption doesn't hold for a raw camera roll — roughly **half** of it is not monitoring material at all, and that junk must be filtered first or it pollutes the suggestion queue.

### The keep/discard rule (learned by correction)

The bar is **narrower than "gardening-related."** Keep only if an **actual living plant of the user's own** is in frame — in a pot/planter/tray, including seedlings, wilted, dying, ugly. Discard, even when green or garden-adjacent:

- Bare soil / potting mix / sand / substrate close-ups with no visible plant
- Empty pots, saucers, drainage trays, stacked planters
- Garden-product packaging (fertiliser/pesticide bottles, soil bags, seed boxes)
- Store / nursery displays: seed-packet racks, plants-for-sale shelves
- Store-bought / bagged herbs with price tags; harvested herbs being washed, weighed, bundled, or on a cutting board
- Cooking / food; kitchen scraps (onion/ginger) sprouting in a pan
- Screens, thermostats, documents

### Calibration numbers (useful for setting auto-filter thresholds)

- **False-keep rate ≈30%** in the first two human-reviewed batches before the rule tightened. The single biggest miscalibration: treating "contains a plant or gardening context" as keep. Requiring an actual living plant would have caught ~1/3 of the over-keeps.
- An aggressive automated discard pass then had a **false-reject rate ≈8%** — genuine potted seedlings wrongly discarded. So an automated gate should **bias toward keep on ambiguous soil/tray shots** and surface them for a cheap human glance rather than hard-deleting.

### Confusable categories a classifier must handle

These are the boundaries that produced nearly all the errors at thumbnail scale:

- **Grains / oats / flour / sawdust vs. soil** — visually identical at 160px; the food versions are the trap.
- **Sparse seedling tray vs. bare-soil tray** — a freshly-sown cell tray reads as "empty soil." Bias keep.
- **Lemongrass / leek / spring-onion stalks** — harvested-on-a-board (discard) vs. growing-in-a-pot (keep) vs. rooting-in-water for propagation (keep).
- **Sprouting kitchen scraps vs. propagation** — onion bottoms in a glass (discard) look like a deliberate cutting (keep).
- **Jars of yellowish liquid** — recurring false-keep (assumed propagation/rooting in water); at least one was not horticultural at all. Default discard unless a plant/cutting is clearly visible in the jar.

**Implication for the pipeline:** add a cheap binary keep/discard gate (thumbnail-grid batching keeps the token cost near-free) ahead of the expensive per-photo tagging. Photos that fail the gate never reach `photo_ai_suggestions`. Ambiguous gate results get a lightweight "confirm import" review, distinct from the richer tagging review.

---

## Session findings & decisions (2026-05-30)

A short research session ran Claude (the Claude Code session itself, reading photos
off disk — see decision 2) over a 6-photo sample spread across the 957-photo set,
to test cold-start suggestion quality. Decisions and findings below **supersede the
original design where they conflict** — the sections further down predate them.

### Decisions

1. **No keep/discard gate.** The Pi only ever produces overhead balcony shots, which
   are by definition monitoring photos of the user's plants. The gate existed solely
   to clean the one-time 2,626-photo phone camera-roll backfill, which is done.
   _Caveat:_ this holds for the **Pi pipeline only**. Batch-tagging `manual`/`phone`
   source photos again would reintroduce junk and need the gate.

2. **Claude Code is the producer, never the Anthropic API.** The backend does not call
   Claude. A Claude Code session reads photos and emits suggestion JSON; the backend's
   only jobs are (a) serve the unclassified list + known units/labels, and (b) ingest
   the JSON into `photo_ai_suggestions`. _Why:_ no API key, no SDK dependency, no
   per-call cost, no rate limits. This **removes the `/assistant/ai-suggestions/batch`
   (sync, Claude API) endpoint** from the design and replaces it with a thin ingest
   path. The earlier "async via shell script" preference falls out naturally: the
   script just ingests a JSON file the session produced. Build shrinks to **ingest +
   review UI**.

3. **Cold start is vocabulary-building, not accuracy.** With most units/labels not yet
   existing, `suggested_plant_id` is null on a cold batch and the value is in
   `suggested_plant_name` (free text) + `question`. The first batches teach the
   taxonomy (and create units/labels on accept); quality climbs as the known-list and
   confirmed-neighbour signals fill in. Expect batch 1 to be messy and convergent.

4. **Batch hints are per-group, not per-photo or per-batch.** A single hint per batch
   is too coarse; per-photo is too tedious. Submit flow: select photos → split into
   groups → one hint per group. No schema change (hint already stored per row).

### Findings from the 6-photo calibration

Scoreboard vs. ground truth: photos 2 (Thai basil), 3 (dill), 4 (lemongrass — my
binary question held the answer), and the sage pot in 5 were **correct**. Photos 1, 5,
6 were a **structural miss** (see below).

- **Known list value is real but bounded.** It confirms mature/distinctive plants
  (dill, sage, Thai basil) and turns confusables into a clean binary that held the
  right answer (lemongrass vs rau ram → lemongrass). It does **nothing** for early
  seedlings.
- **Adding a species (fenugreek) expands the candidate set but does not lift seedling
  confidence.** The bottleneck is leaf-stage resolution, not list coverage.
- **Headline: one photo contains multiple species, arranged spatially.** Photo 1 =
  peppermint (pot) + fenugreek + rocket/cilantro (one trough, split) + parsley/dill
  (another trough, split). Photo 5 = sage pot + parsley/dill + rocket/cilantro. Photo
  6 = parsley (top 6 cells) + genovese basil (bottom 6). **The one-photo → one-
  suggestion model is wrong for this dataset.** The unit of tagging is a *region within
  a photo*. No model cleverness recovers "left third is rocket" from seedling pixels —
  it must come from the human (layout hint or drawn region). The note system already
  stores `x,y,x2,y2` rectangles; tagging should **reuse region rectangles to assign a
  species per zone**, turning one photo into N suggestions.
- **Context is unrecoverable from pixels.** Photo 4 being a *new nursery purchase* could
  only come from a hint — validates batch hints.
- **Date is a growth signal.** Capture date + a known sowing/registration date gives
  the plant's age, and age predicts expected growth stage. This cuts both ways: (a) it
  helps disambiguate seedlings — "12 days from sowing" rules in/out species by expected
  size and leaf stage, narrowing what vision alone can't; and (b) running it forward,
  a registered container's age predicts what a new photo *should* look like, so a photo
  that lags (or races ahead of) the expected stage is itself a condition signal
  (stunting, leggy stretch, vigorous growth). Feeds both the "what" axis (age as a prior
  for species) and the "how's it doing" axis (actual vs. expected stage).

### Round 2 — priors applied (second 6-photo sample)

A second sample was read with the **batch-1 priors active**: the confirmed plant set
(peppermint, Moroccan mint, fenugreek, rocket, cilantro, parsley, dill, sage, Thai &
genovese basil, lemongrass, chives, rosemary, sorrel, rau ram, chilli…) and the
expectation that one photo holds several species.

Scoreboard vs. ground truth: confidently-named mature plants were right (lemongrass,
rosemary, parsley, the basils, chives). Three confusable photos were posed as binary
questions, and **all three brackets contained the true answer** — chives (vs Welsh
onion/garlic chives), chilli (vs basil seedling), rau ram (vs sorrel). The misses were
(a) peppermint-vs-Moroccan-mint species, and (b) undercounting secondary species at
frame edges.

- **The confusable-binary mechanism is validated.** When Claude can't decide, it poses
  a tight question; the human picks. 3/3 of the offered sets contained the truth. The
  metric that matters is **recall of the offered set**, not the model's own pick — keep
  the question format, and bias it toward *including* a candidate rather than committing.
- **Container shape/type carries species.** The same-looking mint is *peppermint in a
  pot* vs *Moroccan mint in a trough*; the human disambiguates by container, not leaf.
  So the container is not just "which unit" — it *is* part of the species identity. Once
  the trough is registered as Moroccan mint, the mint ambiguity is gone — but only the
  container→species binding persists, **not** where the trough sits (the user moves pots;
  see the "what vs. how's it doing" reframe below).
- **Delete must be a first-class review action.** One photo was a soil-moisture test
  shot to bin — neither tag nor keep. Accept / Edit / Reject is insufficient; the review
  UI needs **Delete**. (Also: even the `manual` source set contains non-plant test
  shots, so "no gate" ≠ "no junk ever.")
- **Zone undercounting is the consistent real miss.** Claude reliably names the dominant
  plant(s) but drops secondary species at the frame edges. This is the multi-species /
  region problem again, and the fix is region-level tagging + per-container layout, not
  a better single-label guess.

### Round 3 — priors applied (third sample), and two new signals

Strongest round: the confusable-binary held a 4th/5th/6th time (peppermint vs Moroccan
mint, rau ram vs bolted mint, parsley vs cilantro), and all mature basils were correct.
The single miss was **stage/context, not species**: a pot of peppermint freshly moved
from water to soil (a propagation transplant, stressed) was read as "seedlings." That
distinction is not in the pixels — it's in the timeline.

**Date is the missing primary signal (and it's load-bearing).** A capture date sitting
just after a known propagation/sowing event resolves exactly the ambiguity vision can't:
seedling vs transplant vs mature, and "is this read even plausible for this plant's age?"
Implications:

- The persistent inventory should be **time-indexed per unit**, not a flat list: sown /
  propagated / purchased / died dates. A session aligns each photo's capture date against
  the unit timeline to infer expected stage and flag implausible reads.
- This is also the **staleness fix**: don't trust a static plant list — reason from photo
  dates about what was alive and at what stage on that date.

**Rotation as a suggestion (or auto-fix).** The `rotation` field (0/90/180/270) already
exists in the DB and all write paths. A tagging pass should read with stored rotation
applied, detect when upright orientation disagrees, and **emit a suggested rotation**
alongside the species suggestion — auto-fix on high confidence, queue the rest. It also
improves Claude's own reads on subsequent passes. Add an optional `suggested_rotation`
to the suggestion schema.

### State persistence between sessions (two-tier memory)

Every future session starts cold (reads docs, nothing else), so persistence must target
"what a cold session will reliably find and act on." Two tiers, different lifecycles:

- **Tier 1 — distilled, always loaded.** A dedicated `docs/tagging-calibration.md`
  (separate from this design doc — different churn rate). Holds: the known-plant
  inventory **with varieties and dates** (time-indexed, per above); the confusable rules
  learned by correction (peppermint=pot/Moroccan mint=trough; fine grassy allium → ask
  chives/Welsh onion/garlic chives; lobed apiaceae seedling → parsley vs cilantro;
  reddish-node stem cutting → lemongrass vs rau ram); and meta-heuristics (offer binary
  questions — they bracket the truth; vision reliable on mature/distinctive, useless on
  seedlings; watch frame edges for undercounted zones; keep "unknown" open rather than
  forcing a wrong binary; species errors are rare, stage/context errors are the live
  failure mode).
- **Tier 2 — raw, queried on demand.** The `photo_ai_suggestions` table itself: every
  `(photo → suggestion → confidence → human verdict/correction)` triple. This is already
  the design — the human correction is the training label. It enables (a) **few-shot
  priming** (about to tag mints → pull past confirmed mint photos as visual examples) and
  (b) **confidence calibration** (track stated confidence vs correctness → auto-accept
  high-confidence, only surface medium/low — the thing that makes 1,000 photos tractable).

**Bridge:** a recurring **distillation step** — after a tagging session, review the last
N corrections and propose updates to Tier 1. Tier 2 grows unboundedly and can't be read
whole; Tier 1 stays compact and is what loads cold, refreshed from the data.

**Caveat:** Tier 1 prose goes stale (plants die, new purchases, pots move). Treat the
doc's list as a hint; the DB (`growing_units`, time-indexed) is the source of truth.
Verify Tier 1 against live data — by date — before trusting it.

### The reframe: "what" vs. "how's it doing"

Two things were tangled together in the original design; they have **different
persistence**, and that distinction is the whole point:

- **Container → species binding: persistent.** "This specific trough *is* Moroccan
  mint", "that pot *is* peppermint." Holds until the container is repotted/resown. The
  pot carries its plant wherever it goes. This is the durable asset (a `growing_unit`),
  and it's what fixes the seedling case — register it at sowing, when the human knows
  what went in, and vision never has to ID a cotyledon.
- **Spatial layout: ephemeral.** Where pots sit, and where they land in a photo,
  **changes constantly because the user moves pots around.** A layout is therefore only
  as persistent as a *hint* — valid for the session it was captured in, not a registered
  fact. **Do not persist layouts.**

So the two axes are:

- **"What is it?" — persistent per container, ephemeral per position.** Species is a
  stable property of the *container*, not of a screen location. Knowing the species is a
  lookup *once you know which container you're looking at* — and that mapping is the hard,
  non-persistent part.
- **"How's it doing?" — dynamic.** Wilting, aphids, new growth, flowering. Visible per
  photo; what each new photo genuinely adds, and where Claude stays useful.

The catch: **position ≠ identity.** Because pots move, the Pi's fixed overhead mount
gives consistent *framing* but does **not** tell you which container is which — an
earlier draft of this doc claimed it did; that was wrong. Identifying the container in a
given photo needs either visual recognition (hard: identical terracotta troughs) or a
per-session human link (hint-level). Container→species invalidates only on repot/resow/
harvest events; the photo→container mapping is re-established every session.

_Implied schema direction:_ the durable record is `growing_unit` (container → species),
**not** a stored layout. `photo_ai_suggestions` rows gain an optional bounding box so a
photo can carry several region-level suggestions, and each region is linked to a
`growing_unit` per-photo (ephemeral), not via a persisted layout.

---

## Claude-assisted tagging

### Flow (current)

```
Unclassified photos (+ optional per-group hint, known plants, calibration state)
  → A Claude Code session reads them and emits suggestion JSON (region-level)
  → Ingest writes rows to photo_ai_suggestions   [ingest = script or endpoint, see below]
  → Review UI shows each suggestion alongside its photo/region
  → Human: Accept / Edit / Reject / Delete   (Accept may create a growing_unit/label)
  → Confirmed values move to photos, photo_growing_units, photo_labels
```

Claude never writes the final tables directly — only `photo_ai_suggestions`; human
review moves values across.

**Producer & ingest are not (necessarily) an API.** The producer is a Claude Code
session, not a backend Claude call. Ingest can be the simplest thing that works — a
script writing rows directly to the DB — so **don't assume an HTTP API**. If on-demand
runs are wanted later, a thin endpoint is one option, not a requirement. Decide when
building, not now.

> Batch hints, temporal context, and the structured-response shape below are unchanged
> from the original draft and still apply.

### Batch hints

The hint input is the key feature. Without it, Claude guesses blind. With it, accuracy jumps dramatically.

Examples:
- `"These are from delivery day — probably rau ram and sorrel arriving"`
- `"Balcony session, mostly herbs on the shelf"`
- `"Repotting session — expect root balls and disturbed soil"`
- `"Check for stress — I was away for a week"`

Hint is stored with each suggestion row so the reasoning is auditable.

### Temporal context Claude receives

For each photo, the prompt includes:
- Thumbnail (base64, 256px — already served by `/assistant/photos/{id}/vision-context`)
- Batch hint (if set)
- Photos captured within ±5 minutes: their IDs, timestamps, and any already-confirmed plant associations
- Known growing units list (names, types, varieties)
- Existing labels on this photo (if any)

This means if photo A in a burst is confidently identified as sorrel, photo B taken 30 seconds later gets that as a strong prior.

### Claude's structured response

```json
{
  "suggested_plant_id": 12,
  "suggested_plant_name": "Sorrel",
  "confidence": "high",
  "suggested_photo_type": "health_check",
  "suggested_labels": ["delivery_stress", "wilting"],
  "question": null,
  "observation": "Plant is dramatically drooping over pot sides, reddish stems, consistent with transplant shock."
}
```

When `confidence` is `"low"`, `question` is populated:
```json
{
  "suggested_plant_id": null,
  "confidence": "low",
  "question": "The long flat leaves resemble either lemongrass or garlic chives. Which is registered on this balcony?",
  "observation": "Cannot distinguish without knowing the known-plant list variants."
}
```

Questions are shown in the dashboard review UI and the user can answer inline, which re-runs the suggestion for that photo.

### DB schema

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

Notes:
- **`suggested_plant_id` is usually NULL at cold start** (units mostly don't exist yet); the real output is the free-text `suggested_plant_name`. Accepting can *create* a `growing_unit`, not just link one.
- **Region-level:** `x/y/x2/y2` reuse the note-rectangle convention. One photo → many rows. NULL bbox means the suggestion is about the whole photo.
- **`status = 'deleted'`** records a review decision to bin the underlying photo (test/process shots that are neither tag nor keep).
- `edited_*` fields hold the human's corrections if they chose "Edit".

### Surfaces needed (minimal, transport-agnostic)

Not a fixed API — just the operations the review UI needs against
`photo_ai_suggestions`. Whether these are HTTP endpoints, a script, or direct queries is
a build-time decision (see "Producer & ingest" above).

- **Ingest** a batch of suggestion rows (produced by a Claude Code session).
- **List** pending suggestions with their photos/regions.
- **Resolve** a suggestion: accept / edit / reject / delete. Accept writes through to
  `photos.photo_type`, `photo_growing_units`, `photo_labels` (and may create a
  `growing_unit`/label) in one transaction; delete bins the underlying photo.

> The original draft listed `/assistant/ai-suggestions/batch` (which *ran* Claude
> server-side) — **cut**, since Claude Code is the producer and the backend makes no
> Claude calls.

### Web UI — review panel

The dashboard gets a new **"Review" tab** (or sidebar panel):

```
┌─────────────────────────────────────────────────────┐
│ Unreviewed suggestions: 14                          │
│ Batch hint: [                              ] [Run]  │
├───────────────────┬─────────────────────────────────┤
│  [Photo thumbnail] │ Suggested: Sorrel               │
│                   │ Type: health_check               │
│                   │ Labels: delivery_stress, wilting │
│                   │ Confidence: high                 │
│                   │ "Plant dramatically drooping..." │
│                   │                                  │
│                   │ [Accept] [Edit] [Reject]         │
├───────────────────┼─────────────────────────────────┤
│  [Photo thumbnail] │ ⚠ Question:                     │
│                   │ "Long flat leaves — lemongrass   │
│                   │ or garlic chives?"               │
│                   │                                  │
│                   │ [Answer: ___________] [Rerun]   │
└───────────────────┴─────────────────────────────────┘
```

Keyboard shortcuts: `A` accept, `E` edit, `R` reject, `D` delete (bin a non-plant /
test shot), arrow keys to navigate. Same pattern as the existing photo modal. The mockup
above predates region-level tagging — a real photo may show several suggestions, one per
region.

---

## Capture queue (Pi integration)

> **Scope (2026-05-30): deferred.** The gap rules below are pre-Pi guesses. Don't build
> them until real Pi capture behaviour exists — see "Build order". The section is kept
> as reference, not a commitment.

### Purpose

Build this before the Pi arrives so it's ready on day one. The Pi auto-captures overviews on a schedule; the system tells it what to photograph next and why. This closes the loop: Claude analyses overviews → flags gaps or concerns → Pi captures follow-up → Claude reviews again.

### Gap detection rules

The backend evaluates these rules against current DB state to produce capture requests:

| Rule | Trigger | Suggested shot |
|---|---|---|
| Stress label with no follow-up | Plant has `wilting`/`sulking`/`delivery_stress` and no photo in last 3 days | `health_check` overview |
| Incident with no resolution | `aphids`/`pest_damage` label and no follow-up photo | `closeup` of affected area |
| No photo in 7+ days | Growing unit has no photo this week | `overview` |
| Unregistered plant visible | Photo with `multi_plant` flag and no plant association | `overview` of each pot individually |
| Post-repot gap | `root_bound` label and no photo since event date | `health_check` |
| New purchase with no follow-up | `new_purchase` or `delivery_stress` and no photo 48h later | `health_check` |

### Capture request schema

```sql
CREATE TABLE capture_requests (
    id SERIAL PRIMARY KEY,
    growing_unit_id INTEGER REFERENCES growing_units(id),
    plant_name TEXT,               -- for unregistered plants
    suggested_shot_type TEXT NOT NULL,  -- overview / closeup / health_check
    reason TEXT NOT NULL,
    priority INTEGER DEFAULT 2,    -- 1=urgent, 2=normal, 3=low
    source_photo_id INTEGER REFERENCES photos(id),  -- photo that triggered this
    status TEXT NOT NULL DEFAULT 'open',  -- open / captured / dismissed
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
```

### API

```
GET /assistant/capture-queue         → open requests, ordered by priority
PATCH /assistant/capture-queue/{id}  → mark captured or dismissed
```

The Pi checks `GET /assistant/capture-queue` before each session. When it captures a photo that satisfies a request, it POSTs the photo and patches the request `status: captured`.

### Web UI — capture queue panel

Second tab in the Review panel:

```
┌─────────────────────────────────────────────────────┐
│ Capture queue: 4 open                               │
├─────────────────────────────────────────────────────┤
│ ● URGENT  Rau ram — health_check                    │
│   "Last photo (104) shows severe wilt. 2 days ago." │
│   [Dismiss]                                         │
├─────────────────────────────────────────────────────┤
│ ● NORMAL  Dill — closeup                            │
│   "Aphid infestation documented (photo 66). No      │
│    follow-up since."                                │
│   [Dismiss]                                         │
├─────────────────────────────────────────────────────┤
│ ● LOW     Lemon thyme — overview                    │
│   "No photo since stress event. Recovery unclear."  │
│   [Dismiss]                                         │
└─────────────────────────────────────────────────────┘
```

---

## What this enables end-to-end

```
Pi captures overview on schedule
  → photo uploaded, enters unclassified queue
  → Claude runs on it (or user triggers batch)
  → suggestion: "Rau ram, health_check, wilting"
  → user accepts in 2 keystrokes
  → capture queue sees: wilting + no follow-up in 3 days
  → capture queue adds: "Rau ram closeup, urgent"
  → Pi (or you) captures closeup
  → repeat
```

The human stays in the loop at the tagging step and the capture step. Claude handles the pattern recognition and the gap detection. You handle the judgment calls — which is exactly how the manual session above worked.

---

## Build order

**Tagging (build now):**
1. `photo_ai_suggestions` table + migration (region fields, `suggested_rotation`,
   nullable `suggested_plant_id`, `deleted` status).
2. Ingest path for suggestion rows — start with a script (no API unless a need appears).
3. List pending suggestions (with photos/regions).
4. Review UI — accept / edit / reject / **delete** + keyboard shortcuts.

**Capture queue (defer):** keep the design here for reference, but **do not build the gap
rules yet** — they're guesses until real Pi behaviour exists. At most, stub the
`capture_requests` table + a trivial list/resolve surface if something needs to write to
it; add real rules only after observing actual Pi captures.

---

## Open questions

- Should the batch suggestion endpoint be synchronous (wait for Claude) or async (job queue + polling)? For 70 photos, sync is fine. For ongoing Pi imports at scale, async is better.
- Should `capture_requests` be auto-generated on a schedule, or triggered manually after each import batch?
- Do we want a mobile-friendly review UI for quick yes/no from the phone, or is desktop-only fine for now?
