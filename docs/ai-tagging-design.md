# AI-Assisted Tagging — Design & Handoff

_Status: active. Plan rewritten 2026-05-31 after the 256px contact-sheet pipeline failed in
a live run. The old grid/batch-size approach is superseded — see Appendix B._

---

## How to use this doc (read first)

1. **"Current plan" is authoritative** — what to do today. Where it conflicts with the
   Appendices, this wins.
2. **Verify plant/container state against the live DB** (`GET /assistant/growing-units`),
   not prose. The DB needs cleanup (see "Closed set").
3. **Appendix A** = confirmed few-shot examples (reference material). **Appendix B** =
   dated evidence log of how we got here. Evidence, not instructions.

---

## TL;DR — the plan

Two phases. Identity comes from **priors**; vision **confirms and reads condition**.

- **Phase 1 — backfill (now).** Classify the ~901 unclassified historical phone photos via
  the **Anthropic Batch API**, **Sonnet @ 1024px**, **individual images** (not a grid),
  **container-first** matching + a **SEEDLINGS** fallback, with a compact prior-laden cached
  prompt. Flag confusables/low-confidence → second **Opus** batch → agreement gate → humans
  review only the disagreements. **Output: a classified archive + a container/composition
  registry.** Cost ≈ **$25**.
- **Phase 2 — Pi monitoring (when the Pi is up).** Fixed-camera overhead shots → a
  **self-maintaining layout map** (diff each frame against the last known-good to detect and
  localize what moved) → **region tagging + harvestability estimation**. This is the
  recurring payoff; the Phase-1 registry seeds it.

The whole design changed because the constraint changed: see "Budget reframe".

---

## Why the old plan was binned (2026-05-31)

256px contact-sheet grid + cheap model + open-world ID + self-reported confidence as the
gate. A live run produced garbage: **44% precision on the model's own high-confidence tier**;
"lemongrass" dumped as a catch-all (~78% of high-confidence lemongrass calls wrong);
sage→basil (a *distinctive* plant); fringe-plant tagging on multi-plant shots; and likely
photo-ID mis-mapping across grid cells (the model transcribing the wrong cell's ID).

Root causes, in order of impact:
1. **256px starved the model** — resolution was the dominant killer.
2. **Open-world** ("what plant is this?") instead of **closed-set** ("which of my plants?").
3. **No composition prior** — each region guessed in isolation.
4. **Self-confidence as the gate** — anti-calibrated; the model was most confident exactly on
   the confusables it got wrong.

Don't rebuild any of that. The grid is dead.

---

## Findings that drive the new plan

- **Resolution ladder (same overhead shot at 256 / 512 / 1024):** 256 = green blobs, nothing;
  512 = dominant plant *type* nameable; 1024 = some *variety* splits (cilantro vs parsley)
  **and** condition/count detail. Big jump is 256→512; 1024 adds variety + condition. Variety
  pairs with **no** morphological difference (lemon thyme vs thyme; the three chillies) never
  resolve from pixels at any resolution — composition only.
- **Budget reframe (the unlock).** The 256px constraint existed *only* because the producer
  was a Claude Code session on the **Max $100 subscription quota**. The **Batch API bills
  dollars**, and at ~$3/$15 per MTok (Sonnet, −50% batch) classifying 901 photos at 1024px is
  **~$9** (Opus on the flagged subset ~$15 → **~$25 total**). So the resolution-vs-budget
  tension evaporates: use 1024 + capable models. Verify current per-MTok prices before
  running; output tokens dominate Opus cost, so keep JSON terse.
- **Priors carry identity; vision confirms.** A prior-carrying reader called *thyme* where a
  blind reader guessed *rosemary* — same pixels. Priors must also survive **degraded/blurry**
  frames (sharpness is not the gate).
- **Cross-read agreement, not self-confidence, is the trust signal.** Cilantro was
  trustworthy because Sonnet + Opus + the rocket/cilantro composition prior all agreed;
  sage→basil was a lone confident-wrong call. Gate on agreement.

---

## The prior stack (cheapest first; each kills a failure mode)

1. **Closed-set inventory** — the 23 plants below. Match, don't free-guess.
2. **Container composition map** — the highest-value prior (below). Plants co-occur in known
   groupings; composition is durable (travels with the container; changes only on
   repot/resow), unlike screen position.
3. **Container identity by appearance** — containers have been physically stable historically,
   so a container's own look (specific trough/pot) is a recognition anchor *where containers
   look distinct*; identical terracotta troughs fall back to composition.
4. **Pot-morphology / arrangement** — cluster of small pots ⇒ likely chillies; cell tray ⇒
   seedlings; trough vs round pot.
5. **Temporal aging / track** — a later clear frame upgrades an earlier `SEEDLINGS` tag;
   growth trajectory also resolves seedling-vs-transplant-vs-mature.
6. **Resolution ≥512** (1024 for variety/condition) — cheap on the API.
7. **Fixed-camera layout map + change-diff** — Phase 2.
8. **Cross-read agreement gate** — Sonnet + Opus (+ composition); disagreement → human.

---

## Closed set (authoritative — 23 plants)

**Distinctive (a confident single label is OK):** Dill, Parsley, Rocket, Rosemary, Sage,
Sorrel, French tarragon, Fenugreek, Lemongrass (when mature).

**Confusable / variety groups (`options` only — never a confident single pick):**
- Mints: **Peppermint / Moroccan mint**
- Allium clumps: **Chives / Garlic chives / Welsh onion**
- Apiaceae seedlings: **Parsley / Cilantro**
- Basil: **Basil (sweet/genovese) / Thai basil**
- Chillies: **Bird's eye / Hangjiao H7 / Hangjiao H4** — pixel-identical; variety is a
  composition/which-pot lookup, never a vision call
- Stem cuttings / sprawl: **Lemongrass / Rau ram**, and **Sorrel / Rau ram**
- Small woody: **Thyme / Lemon thyme** (not visually separable; options unless container known)

**DB cleanup required before running** (noise from the failed calibration accepts): drop the
spurious **Spearmint** unit (not a real plant); merge **Basil / Genovese basil / Thai basil
vendita** → canonical **Basil + Thai basil**. Verify against `growing_units`.

---

## Container / composition registry (the map)

The durable asset. Largely fixed historically; **may change later** — the registry must be
re-registerable, and Phase 2 detects change by diffing frames.

| Container | Contents |
|---|---|
| Trough | dill + parsley + chives |
| Trough | 2 Basil (genovese) + 1 Thai basil |
| Trough | rocket + cilantro |
| Trough | Moroccan mint (solo) |
| Small trough | Welsh onion (seedlings) |
| Small trough | cilantro (solo) |
| Small trough | fenugreek (solo) |
| Small trough | thyme + lemon thyme |
| Round pots | **one plant each** — peppermint, rosemary, sage, sorrel, rau ram, lemongrass, French tarragon, garlic chives, etc. |
| Trays | tiny seedlings (basil / chilli / parsley / cilantro by date) |

Each trough has a near-unique **composition signature** (grassy + broad-lobed + feathery → the
chives/parsley/dill trough; two basil textures → the basil trough; lobed seedlings + arugula →
the rocket/cilantro trough). Matching the container and looking up its contents is far more
reliable than per-plant botany — and it dissolves the variety problem (Basil vs Thai is a
lookup, not a leaf call).

**Priors are hints, not facts.** A photo may show a moved pot or a replanted trough. If what's
visible doesn't match a known composition, say so — do not force the expected answer. (We
watched a model call basil "Moroccan mint" purely off the trough hint.)

---

## Tagging unit (decided)

- **Troughs → container-first.** Match by appearance + composition → inherit the known
  contents. Don't ID each plant.
- **Round pots → plant-level ID.** Single subject; confusables → `options`.
- **Seedlings / trays → the SEEDLINGS ladder** (below).

### The SEEDLINGS ladder

Never force a species onto a seedling you can't actually see. Graded by confidence:
- **low → `SEEDLINGS`** (generic, no species) — the default for any young/ambiguous sprout.
- **medium → genus/group as `options`** — e.g. `allium seedlings`, `apiaceae (parsley/cilantro)`,
  `basil/chilli seedling`.
- **high → exact species** — only when the leaves are genuinely clear, **or** the container
  composition/date pins it (cilantro-only small trough → cilantro; Welsh-onion trough → Welsh
  onion).

A `SEEDLINGS` tag is a known-unknown, **upgraded later** as the plant grows (a clear frame
back-propagates) or by its container's contents. Seedlings stop producing confident-wrong
garbage.

---

## Phase 1 — backfill pipeline (Batch API)

0. **Curate inputs (done above):** closed set + container map confirmed; clean DB dupes first.
1. **Group the 901 by session** (capture-time gaps, ~15 min) for ordering + provenance only.
   Send **individual 1024px images, one per request** — *not* a downscaled grid (this kills
   the cell-ID mis-mapping bug). Composition priors still work because a single multi-plant
   photo carries multiple regions in one image. (`scripts/prepare_tagging_run.py` provides the
   grouping; the image/transport step changes from contact-sheet to per-image batch.)
2. **Submit a Sonnet Batch API job** with a **cached** system prompt (priors + closed set +
   container map + schema). One photo per request → JSON array of region/container objects.
3. **Ingest** results → `photo_ai_suggestions`, stamping `run_id` / `batch_id` (in
   `prompt_context` until columns exist).
4. **Triage + agreement gate.** Auto-accept only distinctive, high-confidence, single-option
   calls. Everything with `options`, low/medium confidence, a confusable, or `SEEDLINGS`
   beyond the floor → a **second Opus batch on just those**. Sonnet + Opus agree → accept;
   disagree → human review queue.
5. **Humans review only the disagreements** — a fraction of 901.

Cost ≈ Sonnet pass ~$9 + Opus on the flagged subset ~$15 = **~$25**. Batch API is async
(~24h) — fine for a one-time backfill.

**Pre-flight (do before the full 901):** a **thin-vs-rich prior A/B** on 30–50 photos — one
batch with just the species list + schema, one with the full container map — comparing review
time and wrong-option rate. This measures the real risk: does the rich prior *help*, or make
the model **hallucinate the expected composition**? Keep priors compact (a matrix, not an
essay); long prose makes the model obey stale hints.

### The Phase-1 prompt (system, cached across all requests)

```
You identify plants in photos from ONE person's balcony herb garden. CLOSED-SET task:
every photo shows plants from the KNOWN LIST. MATCH to the list — do not identify plants
in general, and do not free-guess outside it.

KNOWN PLANTS (only valid labels):
  Distinctive: dill, parsley, rocket, rosemary, sage, sorrel, French tarragon, fenugreek, lemongrass
  Confusable groups (use options): peppermint/Moroccan mint · chives/garlic chives/Welsh onion ·
    parsley/cilantro · basil/Thai basil · bird's-eye/Hangjiao-H7/Hangjiao-H4 chilli ·
    lemongrass/rau ram · sorrel/rau ram · thyme/lemon thyme

CONTAINER MAP (HINTS, not facts — pots move and troughs get replanted):
  trough: dill + parsley + chives
  trough: 2 basil + 1 Thai basil
  trough: rocket + cilantro
  trough: Moroccan mint (solo)
  small trough: Welsh onion (seedlings) | cilantro (solo) | fenugreek (solo) | thyme + lemon thyme
  round pots: one plant each (peppermint, rosemary, sage, sorrel, rau ram, lemongrass, French tarragon, garlic chives…)
  trays: tiny seedlings
  → If a trough's visible composition matches a known one, prefer that grouping. If it does
    NOT match, say so — never force the expected plants.

RULES:
1. MATCH, don't free-guess. Resembles something off-list ⇒ it's almost certainly the nearest
   KNOWN plant. "unknown" only if nothing fits.
2. Do NOT over-assign a common label (a past run dumped "lemongrass" on anything long/thin).
   Unsure between candidates ⇒ options, never a confident single guess.
3. One photo usually shows SEVERAL plants/zones. Output one object PER plant/zone. Scan all
   four edges — secondary plants at the frame edge are the most-missed.
4. CONFUSABLES ⇒ fill `options` (2–3), not a single pick. Disambiguate by container where the
   map allows (pot=peppermint, trough=Moroccan mint).
5. SEEDLINGS: never force a species. plant="SEEDLINGS" by default; only narrow to a genus
   (options) with decent confidence, or to a species if the leaves are clear OR the container
   composition pins it.
6. CONFIDENCE is honest. "high" only for distinctive, unambiguous mature plants. Anything in a
   confusable group is at most "medium" and carries options. Confidence is NOT permission to
   guess.
7. NON-PLANT (bare soil, tools, test/process, food, screens): plant=null, photo_type=null,
   labels=["delete_candidate"], say why. Do NOT set photo_type to "delete".
8. Note CONDITION/STAGE in observation: seedling/young/mature/flowering; wilting/yellowing/pests.
9. suggested_rotation if the image is clearly mis-oriented.

OUTPUT — ONLY a JSON array, one object per plant/zone:
[
  { "plant": "<known name | SEEDLINGS | null>",
    "options": ["…"],                 // [] if confident
    "confidence": "high|medium|low",
    "photo_type": "overview|health_check|closeup|null",
    "labels": [],                      // e.g. ["seedling"], ["delete_candidate"]
    "region": [x,y,x2,y2],             // normalised 0–1; null = whole photo
    "observation": "<≤8 words: stage/condition>" }
]
No prose outside the array.
```

---

## Phase 2 — Pi monitoring (future): region tagging + harvestability

> Build only once real Pi capture behaviour exists. This is the recurring payoff; the
> Phase-1 registry seeds it.

The Pi gives a **fixed overhead frame**. That doesn't make the layout static (things shuffle)
— it makes **change cheap to detect and localize**:

- **Diff each frame against the last known-good.** Unchanged regions **carry identity forward
  for free** (most of the frame). A changed region is **localized and re-identified on just
  that crop** (cheap), or flagged "something moved here — confirm".
- So layout maintenance flips from "periodically re-register everything" (a chore that won't
  get done) to **self-maintaining via diff**.

On top of that runs the actual goal:

- **Region tagging + harvestability estimate per region.** Identity is free from the map, so
  vision spends entirely on the valuable read: *is this region ready to harvest, and roughly
  how much?* Needs **per-species harvest criteria** + the **growth track** (size/coverage over
  time from the consistent framing). This is the "how's it doing" axis extended to "is it
  pickable" — the live, recurring value that justifies Phase 1's registry work.

---

## DB schema

```sql
CREATE TABLE photo_ai_suggestions (
    id SERIAL PRIMARY KEY,
    photo_id INTEGER NOT NULL REFERENCES photos(id),
    model VARCHAR(100) NOT NULL,
    batch_hint TEXT,
    prompt_context JSONB,          -- priors sent; also holds run_id/batch_id until columns exist
    x REAL, y REAL, x2 REAL, y2 REAL,   -- normalised region bbox (NULL = whole photo)
    suggested_plant_id INTEGER REFERENCES growing_units(id),  -- usually NULL at cold start
    suggested_plant_name TEXT,     -- free text / "SEEDLINGS"; primary output until units exist
    suggested_photo_type TEXT,
    suggested_rotation INTEGER,    -- 0/90/180/270
    suggested_labels JSONB,
    suggested_options JSONB,       -- candidate names for confusables (migration 0011)
    confidence TEXT,               -- high / medium / low
    question TEXT,
    observation TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending / accepted / edited / rejected / deleted
    edited_plant_id INTEGER REFERENCES growing_units(id),
    edited_photo_type TEXT,
    edited_labels JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);
```

- One row **per region**; a multi-plant photo yields several rows. NULL bbox = whole photo.
- `suggested_plant_id` usually NULL at cold start; accepting can *create* a `growing_unit`.
- `status='deleted'` bins the underlying photo (junk/test shots).

## Surfaces

Operations the review UI needs against `photo_ai_suggestions`:
- **Ingest** a batch of rows (produced by a Claude Code session or the Batch API job).
- **List** pending suggestions with photos/regions.
- **Resolve**: accept / edit / reject / delete. Accept writes through to `photos.photo_type`,
  `photos.rotation`, `photo_growing_units`, `photo_labels` (may create a `growing_unit`/label)
  in one transaction; delete bins the photo.

## Build status

**Done:**
1. ✅ `photo_ai_suggestions` table + migration (region fields, rotation, options, deleted status).
2. ✅ Ingest — `scripts/ingest_suggestions.py` + `POST /suggestions/ingest`.
3. ✅ `GET /suggestions` (list pending) and `PATCH /suggestions/{id}` (accept/reject/deleted;
   accept writes through, creates unit/label as needed).
4. ✅ Review tab — region overlays, keyboard nav, inline edit, `suggested_options` choice buttons.
5. ⚠️ `scripts/prepare_tagging_run.py` — built, but its **256px contact-sheet grid is
   superseded** (see Appendix B). Reuse only its session-grouping; switch transport to
   per-image Batch API.

**Outstanding (new plan):**
- **Batch API submission + ingest** for Phase 1 (individual 1024px images, cached prior
  prompt, Sonnet). No interactive Claude reads.
- **DB cleanup**: drop spurious Spearmint; merge basil dupes.
- **Container/composition registry** as a first-class store (seeds Phase 2); seed from the map
  above + Appendix A.
- **Agreement-gate triage** (Sonnet vs Opus) + a review queue scoped to disagreements.
- **`run_id`/`batch_id` columns** on `photo_ai_suggestions` (provenance) before scaling.
- **Duplicate-ingest protection** — skip on `(run_id, photo_id, bbox, plant)` match.
- **Session-propagation review actions** ("apply this plant to selected") — human-triggered only.
- **Phase 2**: layout-map + change-diff; region tagging + harvestability. Build when Pi exists.

---

## Capture queue (deferred — reference only)

> Pre-Pi guesses. Do not build the gap rules until real Pi behaviour exists.

The Pi auto-captures overviews; the system tells it what to shoot next. Gap rules evaluate DB
state to produce capture requests (stress with no follow-up → health_check; incident with no
resolution → closeup; no photo in 7+ days → overview; etc.).

```sql
CREATE TABLE capture_requests (
    id SERIAL PRIMARY KEY,
    growing_unit_id INTEGER REFERENCES growing_units(id),
    plant_name TEXT,
    suggested_shot_type TEXT NOT NULL,  -- overview / closeup / health_check
    reason TEXT NOT NULL,
    priority INTEGER DEFAULT 2,
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

- **Photo mix of the 901** — mostly whole-trough shots, mixed (overviews + closeups +
  partials), or wide multi-trough overviews? Affects how cleanly container-matching works
  (the prompt handles all cases via per-region output; this only changes difficulty).
- **Harvestability criteria** — per-species "ready" thresholds need defining for Phase 2.
- Auto-generate `capture_requests` on a schedule, or manually after each import?
- Mobile-friendly review UI, or desktop-only for now?

---

## Appendix A — confirmed few-shot example pool

Ground-truthed across calibration rounds (2026-05-30). Reference material for the confusable
classes; **bootstrap** — migrate to a live `photo_ai_suggestions` query when built. Filenames
under `data/photos/`. Verify against the DB; pots move and plants die.

**Single / dominant subject:**
- `554b3a646dc64b3399b6382c3c81ce68.jpg` — dill, mature, leggy/floppy
- `291ff4b9585540eab4f55c00347d02ca.jpg` — Thai basil, seedlings
- `457790d2c20d4d2090dbf1a87242dcf0.jpg` — genovese basil, seedling
- `c9860a82b9594b83a0f0c1658becc874.jpg` — genovese basil, young plant
- `b2d470329a6f43c9b3f78bd3a5e47837.jpg` — chilli, seedling (guessed basil-or-chilli; chilli)
- `892b874e1bac4f25821c8f744ee3dd9e.jpg` — chives clump (allium binary; chives)
- `19af7b97567d47f8bf32f2a57db45334.jpg` — peppermint, water→soil propagation, stressed (misread as seedlings)
- `7236f3ff21474d17be7ab0e287f728a5.jpg` — rau ram, sprawling/stressed
- `db60aae6b3e6418f99c107c3bf2bc039.jpg` — rau ram, severely wilted (moved indoors)
- `7faf996c30144613a03c21aad20830ee.jpg` — lemongrass cuttings, new nursery purchase

**Multi-species (region-tagged) — also the seed for the composition registry:**
- `000cf7f3d4f64299b2d3dd454fd06eab.jpg` — peppermint (pot), fenugreek (trough), rocket + cilantro (trough), parsley + dill (trough)
- `ac85543fb0e442549ef03b2f6e56d3ff.jpg` — sage (pot), parsley + dill, rocket + cilantro
- `d630dda5ddf643f2bc4ff61df40cefa7.jpg` — parsley + genovese basil (split tray)
- `09923168f26e487992fa7c65a9a1237c.jpg` — Moroccan mint, genovese + Thai basil, Welsh onion, rocket
- `5e43054b5eb545658514a1681c88a1d9.jpg` — dense mixed pot: lemongrass, rosemary, sage, peppermint, genovese basil, sorrel, parsley, chives
- `9b523deb3f3b46db9ecbb8b25916e713.jpg` — parsley / cilantro seedlings (6-cell tray)
- `f6304791e4a64bf18f19172622ec836f.jpg` — Thai basil + genovese basil (one trough)

**Discard:** `34af94c1ded745ee95828eb2a2d41062.jpg` — soil-moisture test close-up → delete

---

## Appendix B — evidence log (chronological)

Dated record of how the plan was reached. Evidence, not instructions — the head supersedes.

### 2026-05-29 → 05-30 — early design & calibration
Trial run + a ~2,626-photo phone backfill (→ ~957 keepers) established: timestamp proximity is
a strong signal; targeted prompts beat generic; varieties are invisible from pixels; one photo
holds several species (tag per region); date is a growth/stage signal; container→species is
the durable binding, screen position is not; "what" (persistent) vs "how's it doing" (dynamic).
Decision: Claude Code session as producer (no backend API calls); no keep/discard gate for the
Pi (overhead monitoring shots), but manual/phone re-tags still need it.

### 2026-05-31 — first live ingest run (42 suggestions) and its failure
256px 3×2 contact sheets, cheap model, open-world, self-confidence gate. Calibration runs
`calib_06/12/20` (same ~57 photos). On the high-confidence tier: **12 accepted / 15 rejected =
44% precision**; "lemongrass" over-predicted (~7/9 wrong); sage→basil; fringe-plant tagging on
multi-plant shots. The pending rows were trimmed (kept calib_06 high-confidence; rest set
`rejected`) and abandoned — they are mis-mapped, not worth reviewing.

### 2026-05-31 — resolution ladder & model comparison
Same overhead shot at 256/512/1024: 256 = blobs; 512 = type nameable; 1024 = variety
(cilantro vs parsley) + condition/count. Sonnet vs Opus vs ChatGPT at 1024 **agreed on all
distinctive plants** (chives, parsley, dill, basil, empty pots) and split only on confusables
(thyme/rosemary, basil/mint) — so a cheap model suffices at adequate resolution, and
**agreement is the gate, not stated confidence**. Sonnet got cilantro right at 1024 (a variety
I'd over-conservatively called unresolvable). The thyme/rosemary split was a **prior gap** (the
prior-carrying reader matched the known inventory; the blind one guessed).

### 2026-05-31 — the pivot (folded into the head)
Budget reframe: the 256px constraint was the **Max quota**, not dollars — Batch API at 1024 is
~$25 for the backlog, so the constraint dissolves. Identity comes from a **prior stack**
(closed set → container composition → container appearance → pot morphology → temporal aging →
agreement gate); vision confirms + reads condition. **Container-first** tagging for troughs,
plant-level for pots, **SEEDLINGS** ladder for trays. Phase 2 (Pi): fixed-frame **change-diff**
layout map + **region tagging + harvestability** — the recurring payoff.
