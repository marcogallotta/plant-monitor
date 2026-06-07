# AI-Assisted Tagging — Design & Handoff

_Status: active. Plan rewritten 2026-05-31 after the 256px contact-sheet pipeline failed in
a live run. The old grid/batch-size approach is superseded — see Appendix B._

---

## Current focus (2026-06-07)

**The product (clarified).** An on-demand *"what's cookable right now, and roughly how much"*
read per plant, served to ChatGPT — identity + rough harvest amount + condition (e.g. "loads of
rocket, ~50 g; Thai basil's flowering, use it now"). Rough *relative* amounts are fit for
purpose; gram-accurate logging is not needed.

**Operating model — two layers that feed each other:**
- **Overhead Pi** = cheap, continuous *index* — identity-by-position (via the map), presence,
  and *gross* change ("region X changed", "rocket hasn't bolted"). It can't read fine detail or
  tell look-alikes apart (a known −20 g dill harvest was invisible from overhead — see Phase 2).
- **Closeups (phone + camera)** = the *value* layer — confident ID + scale + condition + harvest
  read, where overhead gives green blobs. The map gives each closeup its identity by position;
  closeups inherit identity ~free (caveats: confusables + context-less shots need the review
  tail; effect is strongest forward-looking).

**Freshness is first-class.** Every reading carries a date, and decays at a rate set by the
plant's growth speed and microclimate: fast movers (rocket, basil, dill) go stale in days; slow
woody herbs (sage, rosemary, thyme) stay valid for weeks; shade-net plants decay slower than
exposed ones. The overhead keeps dated closeups honest by confirming gross change (e.g. "not
bolted").

**Two-axis prior retrieval.** A photo plays two roles, selected differently:
- **Identity / disambiguation** → use **high-quality reference** images (the `reference` label),
  *age-agnostic*. "High quality" here = **clearly shows the discriminating features** (e.g. the
  lemongrass reference `a377f5` shows the red culms), not merely in-focus.
- **State / harvestability** → use the **most recent** images, quality permitting.
- Prefer photos that are **both**. Retrieval: pull `reference`-labelled shots for the unit (ID)
  + recent shots (state), then combine.

Confirmed photo→unit links live in **`photo_growing_units`**; the **`reference`-labelled** subset
is the curated prior set (supersedes Appendix A's bootstrap list). **Confirmed-only** — never
guesses — so the corpus stays clean and **compounds** as better shots arrive. Seeded 2026-06-07
with reference closeups for lemongrass, garlic chives, rocket, sage, sorrel, tarragon, the basil
trough, and Thai basil vendita.

**Active work, in priority order (reordered 2026-06-07):**
1. **Region-marking the Pi map (now #1).** `photo_notes` + a `growing_unit_id` FK; draw a box
   per pot on a reference frame, assign its unit. **Load-bearing**, because today proved vision
   *confidently swaps* confusables (lemongrass↔garlic chives) and *cannot* tell visually-
   identical varieties apart (the chillis — H4/H7/BE) — only position can. Everything sits on
   this. Record per-pot distinguishing features + pot size (see plants-data.md).
2. **Frictionless phone sync** — the data-volume lever; auto-upload closeups (`source=phone`
   path exists, automation is the gap). The region map makes the inflow identifiable.
3. **Imaging investigation** — does resolution / a closeup make harvest-scale change detectable?
   (Drift ~5°, not the blocker.)

- **Shelved:** the Asana harvest-log ingest — calibration comes cheaper from occasional human
  corrections + closeups than from an ongoing log; the cooking read needs only rough amounts.
- **Done:** layout captured as **region tags in the DB** (`photo_notes.growing_unit_id` on the
  reference frame `2026-06-07T130010Z.jpg`) — the authoritative positions. Plant data
  (status, pot/quantity, confusable features) lives in **[plants-data.md](plants-data.md)**.
  Phase-1 phone backfill paused.

Everything below this section is reference and full design detail.

---

## How to use this doc (read first)

1. **"Current plan" is authoritative** — what to do today. Where it conflicts with the
   Appendices, this wins.
2. **Verify plant/container state against the live DB** (`GET /assistant/growing-units`),
   read positions from the **region tags on the reference frame** (DB), and plant data from
   [plants-data.md](plants-data.md) — not prose.
3. **Appendix A** = confirmed few-shot examples (reference material). **Appendix B** =
   dated evidence log of how we got here. Evidence, not instructions.

---

## TL;DR — the plan

Two phases. Identity comes from **priors**; vision **confirms and reads condition**.

- **Phase 1 — backfill (paused; see Current focus).** Classify the ~901 unclassified historical phone photos via
  the **Anthropic Batch API**, **Sonnet @ 1024px**, **individual images** (not a grid),
  **container-first** matching + a **SEEDLINGS** fallback, with a compact prior-laden cached
  prompt. Flag confusables/low-confidence → second **Opus** batch → agreement gate → humans
  review only the disagreements. **Output: a classified archive + a container/composition
  registry.** Cost ≈ **$25**.
- **Phase 2 — Pi monitoring (active; the Pi is up).** Fixed-camera overhead shots → a
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

## Closed set (authoritative)

**Distinctive (a confident single label is OK):** Dill, Parsley, Rocket, Rosemary, Sage,
Sorrel, French tarragon, Lemongrass (when mature).

**Confusable / variety groups (`options` only — never a confident single pick):**
- Mints: **Peppermint / Moroccan mint** (Spearmint is dead as of 2026-06-06 — retired)
- Allium clumps: **Chives / Garlic chives / Welsh onion**
- Apiaceae seedlings: **Parsley / Cilantro**
- Basil: **Genovese basil / Thai basil**. Note there are **two distinct, real Thai basils** —
  the seed-grown `Thai basil` and the visually-distinctive `Thai basil vendita`. Label both
  "Thai basil", but **always surface them as a binary review choice**.
- Chillies: **Bird's eye / Hangjiao H7 / Hangjiao H4** — pixel-identical; variety is a
  composition/which-pot lookup, never a vision call
- Stem cuttings / sprawl: **Lemongrass / Rau ram**, and **Sorrel / Rau ram**
- Small woody: **Thyme / Lemon thyme** (not visually separable; options unless container known)

**DB cleanup (done 2026-05-31):** merged the generic **Basil** unit into **Genovese basil**
(no plain "basil"). **Kept as real:** **both** Thai basils — `Thai basil` (seed-grown) and
`Thai basil vendita` (a distinct cultivar); the two are a permanent binary on review.

**Update 2026-06-06 (from the balcony walk-down — see [plants-data.md](plants-data.md)):**
`Spearmint` is **dead** (retire it) and **Fenugreek no longer exists** — drop both from all
priors. Units created from the walk-down: **Sage (37), Thyme (38), Chives (39), Cilantro (40),
Cilantro root (41)**. The remaining real plants without a unit (the chilli varieties) get
created on accept, not pre-seeded.

---

## Container / composition registry (the map)

The durable asset. Largely fixed historically; **may change later** — the registry must be
re-registerable, and Phase 2 detects change by diffing frames.

> **Current ground truth: the region tags** on the reference frame `2026-06-07T130010Z.jpg`
> (DB, human-verified 2026-06-07) for positions, and **[plants-data.md](plants-data.md)** for
> plant data. The table below is the historical phone-era registry and is partly stale
> (Fenugreek gone, Spearmint dead, basil/mint placements changed) — keep it only as Phase-1
> backfill context.

| Container | Contents |
|---|---|
| Trough | dill + parsley + chives |
| Trough | 2 Genovese basil + 1 Thai basil |
| Trough | rocket + cilantro |
| Trough | Moroccan mint (solo) |
| Small trough | Welsh onion (seedlings) |
| Small trough | cilantro (solo) |
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
  Distinctive: dill, parsley, rocket, rosemary, sage, sorrel, French tarragon, lemongrass
  Confusable groups (use options): peppermint/Moroccan mint · chives/garlic chives/Welsh onion ·
    parsley/cilantro · genovese basil/Thai basil · bird's-eye/Hangjiao-H7/Hangjiao-H4 chilli ·
    lemongrass/rau ram · sorrel/rau ram · thyme/lemon thyme
  (Two real Thai basils — "Thai basil" and "Thai basil vendita". Label "Thai basil"; always
   present both as a binary on review.)

CONTAINER MAP (HINTS, not facts — pots move and troughs get replanted):
  trough: dill + parsley + chives
  trough: 2 genovese basil + 1 Thai basil
  trough: rocket + cilantro
  trough: Moroccan mint (solo)
  small trough: Welsh onion (seedlings) | cilantro (solo) | thyme + lemon thyme
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

**Region-tagging mechanism (decided 2026-06-06):** reuse `photo_notes`, which already stores a
normalised rectangle (`x, y, x2, y2`, 0–1, range-checked) and ships the full draw/edit UI
(shift+drag region notes, `pendingNote`, `visualToStored()` rotation handling). Add a nullable
`growing_unit_id` FK to `photo_notes` (and make `note_text` nullable) — a region note pointing
at a unit *is* a region tag. This avoids a new `photo_regions` table. A human-verified set of
such notes on one reference frame is both the validation overlay and the reusable layout
template; per-region crops (reuse the rotation-baked crop from `/photos/export`) build the
per-unit dataset. AI-suggested regions continue to live in `photo_ai_suggestions`.

The Pi gives a **fixed overhead frame**. That doesn't make the layout static (things shuffle)
— it makes **change cheap to detect and localize**:

- **Diff each frame against the last known-good.** Unchanged regions **carry identity forward
  for free** (most of the frame). A changed region is **localized and re-identified on just
  that crop** (cheap), or flagged "something moved here — confirm".
- So layout maintenance flips from "periodically re-register everything" (a chore that won't
  get done) to **self-maintaining via diff**.

**Reality check (2026-06-06): a known −20g dill harvest was NOT visually detectable.** Tested
against ground truth — a real **−20g dill harvest** between the `17:00Z` and `18:00Z` frames
(≈19:00–20:00 local) — Claude could not see the change. Initial guess blamed mount drift, but
on re-check the drift is **minor and one-directional** (the mount is a temporary wind-nudged
rig, but the scene is clearly the same arrangement frame-to-frame) — so **drift is not the
cause**. The likely real limiter is **resolution + the overhead angle + dill's wispy,
semi-transparent foliage**: from above a feathery plant has no clean silhouette whose mass is
readable, so even a sizable removal doesn't produce a resolvable change. 20g of dill is a lot
of volume (should be the easy case), so the failure points at the imaging, not the harvest
size. **Open question:** does higher resolution / a less oblique crop / a closeup make
harvest-scale change detectable, or is fine visual harvest-diffing simply not reliable here?
Until that's answered, harvest ground truth comes from **explicit labels** (below), not vision.
Frame registration is still worth doing for clean diffs, but it is **not** the proven blocker.

On top of that runs the actual goal:

- **Region tagging + harvestability estimate per region.** Identity is free from the map, so
  vision spends entirely on the valuable read: *is this region ready to harvest, and roughly
  how much?* Needs **per-species harvest criteria** + the **growth track** (size/coverage over
  time from the consistent framing). This is the "how's it doing" axis extended to "is it
  pickable" — the live, recurring value that justifies Phase 1's registry work.
- **Harvest ground truth = a human-in-the-loop log, not vision (decided 2026-06-06).** The user
  cooks with ChatGPT, which already knows the amounts and writes them to **Asana**: project
  *Plants* → section **Plant Records** → one task per plant → harvest grams as **task comments**
  (e.g. "20g harvested around 19:00" on the Dill task). A sync reads those comments → matches
  the task name to a growing unit (same closed set; Asana "Basil" → Genovese, chillis not on
  the balcony) → creates `harvested` **events**, grams in notes, **idempotent on the Asana
  comment gid** so re-reads don't double-count. **Comment times are local (CEST, UTC+2); photo
  filenames are UTC** — translate when correlating a harvest to a frame. These approximate
  labels are the real harvestability signal while the mount/vision can't measure change, and
  they become the per-species expected-yield data that "ready" thresholds get defined against.

### Pi as a ground-truth generator (the build-order flip)

Fixed camera + pots mostly static + same viewpoint even when they shuffle ⇒ **per-shot delta
is near-zero.** Consequences:

- **One good human-verified reference frame anchors the whole stream.** Later frames inherit
  identity by a trivial diff; the diff only lights up on genuine change (repot/new plant) →
  re-register *that region*. Registration is one-time + self-maintaining, not per-photo.
- **Every Pi frame is a labelled example** (identity is anchored, not guessed). Over weeks
  this builds a per-species, per-stage **visual-prior corpus of the user's actual plants** —
  the reference set Appendix A never had, and the dataset harvestability models train on.
- **Build-order flip:** do the **Pi first as the truth source**; the messy non-Pi phone
  backfill is cheaper *and more accurate* once that corpus exists (use confirmed examples as
  priors). Caveats: overhead→oblique viewpoint transfer is partial (identity/texture carry
  over, exact silhouette less so); the corpus is forward-looking, so it best serves
  current/persistent plants.
- **The whole-scene frame yields comparative features** unavailable in isolated shots: with
  every plant in one frame at one scale/time, *relative* cues disambiguate look-alikes —
  lemongrass **sparse** vs garlic chives **dense** (resolves the grassy-clump confusion), Thai
  basil small, cilantro = the tiny seedlings. These are time-dependent (the growth track
  updates them) but the snapshot captures the current comparative state. Isolated phone
  closeups can't provide this — no shared scale/reference.
- **Growth is *measured*, not inferred.** Don't ask the model to be "clever" about how much a
  plant grew between a shot and the reference (implicit visual reasoning is the flaky path we
  watched fail). The fixed frame makes a region's area/coverage directly comparable over time,
  so growth is a measured number; a simple per-species expected-vs-actual curve then drives
  both anomaly flags (lagging = stunting/stress, racing = vigour) and harvestability (ready at
  a coverage threshold). The model's role stays *interpretation* (e.g. "looks leggy/stressed")
  — a soft overlay on the hard measurement.

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
- ✅ **DB cleanup done**: merged plain `Basil` → `Genovese basil`. Spearmint and both Thai
  basils (`Thai basil` + `Thai basil vendita`) are real — kept.
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
- **Harvestability criteria** — per-species "ready" thresholds still need defining. Harvest
  *amounts* now arrive as ground truth via the Asana → `harvested`-events loop (see Phase 2);
  the open part is the per-species coverage/size threshold that flags "ready".
- **Is harvest-scale change visually detectable at all?** A known −20g dill harvest was
  invisible in the overhead frames (drift ~5°, so not the cause). Test higher resolution /
  closeups before assuming visual harvest-diffing is viable.
- Auto-generate `capture_requests` on a schedule, or manually after each import?
- Mobile-friendly review UI, or desktop-only for now?

---

## Appendix A — confirmed few-shot example pool

Ground-truthed across calibration rounds (2026-05-30). Reference material for the confusable
classes; **bootstrap** — now **superseded by a live query**: confirmed photo→unit links are in
`photo_growing_units`, and the curated high-quality subset carries the **`reference`** label
(see "Two-axis prior retrieval" in Current focus). Prefer that live set over this list. Filenames
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

### 2026-06-06 — Pi is up; Phase-2 groundwork, harvest loop, imaging limit
First real Pi overhead captures (hourly). Did a human-guided **balcony walk-down** → a
verified pot-position map, now in [plants-data.md](plants-data.md) + DB region tags (supersedes this doc's
historical container table). DB updated from it: **Spearmint dead, Fenugreek gone**; created
units **Sage(37), Thyme(38), Chives(39), Cilantro(40), Cilantro root(41)**. Decided **region
tagging = `photo_notes` + `growing_unit_id` FK** (reuse the existing rectangle UI), not a new
table. **Harvest ground-truth loop confirmed working**: ChatGPT (cooking) writes grams as
**comments on per-plant tasks** in Asana *Plants → Plant Records*; read end-to-end via the API
(found "20g harvested around 19:00" on the Dill task). **Imaging limit found:** that same known
−20g dill harvest was **not** visually detectable between the 17:00Z/18:00Z frames; first
blamed mount drift, but drift is only **~5°** (one-directional) — so the limiter is
resolution/overhead-angle/wispy foliage, not the mount. Conclusion: harvest truth from labels
(Asana), not vision, until higher-res/closeups are tested. Note: Pi filenames are **UTC**, user
speaks **local (CEST/UTC+2)** — translate when correlating harvests to frames.

### 2026-06-07 — closeups validated; confusable swap; region-marking promoted to #1
Ran a live closeup-ID experiment. **Closeups work well:** correct IDs on tarragon (leggy),
Thai basil vendita (**flowering** → "use it now"), rocket (big, not bolted), the 2-Genovese+1-
Thai basil trough (by composition), and sage — each giving confident ID + a **scale anchor**
(pot rim) + condition + a usable harvest number, where overhead gave only blobs. This is the
case for the closeup value-layer.

**Freshness/decay confirmed as a real variable.** A rocket closeup was 10 days old; reconciled
via microclimate (under shade net → slow bolting) + overhead cross-check (not bolted) → baseline
still valid. Sage barely decays (slow woody perennial); rocket/basil/dill decay fast. **Don't
infer intent from context** — wrongly read a kitchen-counter shot as "about to harvest"; it was
an *inspection* shot. **Mixed-trough limit:** can't measure an individual plant's growth inside
a shared trough from overhead (the Thai basil was unmeasurable among its trough-mates).

**The decisive failure — confusable swap.** Confidently called two grassy closeups "lemongrass"
(then "both lemongrass" — impossible: only one exists), then split them by a *spurious* feature
(cascade/length) and got them **exactly backwards**. Truth: fat/tall leaves + **bigger pot** =
lemongrass; thin blades = garlic chives. Recovery came only from **hard priors**: the unit
**count** ("one lemongrass"), the **sorrel landmark** (it sits *between* the two), **pot size**,
and leaf **width** — none of them the confident vision call. Rules banked: (1) on confusable
groups, **high confidence is disqualifying**, not reassuring — defer to position/pot/scent and
surface options; (2) **hard count constraints beat soft composition priors**; (3) record the
**discriminating features** per group in the map (done in plants-data.md).

**Chillis = the pure-position case.** Morning frame (07:00Z) shows them back by the door; the
three pots are **H4→H7→BE left-to-right** (units 34/35/36) but **visually identical** — no
vision path exists, identity is position-only. Together with the swap, this **promotes
region-marking the Pi map to the #1 task** (see Current focus). Harvest-log ingest **shelved**;
the product is the rough **cooking-availability read**, not gram-accurate logs.
