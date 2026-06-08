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
1. ✅ **Region-marking the Pi map (was #1, done 2026-06-07).** `photo_notes` + a `growing_unit_id`
   FK and the region-tag UI are built (migration `0013`; draw + unit dropdown + name-on-box),
   and the reference frame `2026-06-07T130010Z.jpg` is fully tagged (25 units). This was
   load-bearing because vision *confidently swaps* confusables (lemongrass↔garlic chives) and
   *cannot* tell visually-identical varieties apart (the chillis — H4/H7/BE) — only position can.
   Per-pot distinguishing features + pot size live in plants-data.md.
   **Next on this line:** the Phase-2 diff/inherit step that carries these tags forward to later
   frames (see Phase 2 below). Two foundations are now built (2026-06-07): **frame registration**
   (`scripts/frame_registration.py` — aligns a new frame onto the reference so tags warp forward)
   and **sway suppression at capture** (`pi/capture.py` — each capture is a 10-frame burst collapsed
   to a mean plate, ~60–69% less foliage-sway noise). The **lighting-robust change signal** is now
   **method-found** (Finlayson illuminant-invariant, validated on a known harvest — see Phase 2), but
   the verdict awaits a **harvest bracketed by plates** (current data is pre-plate/noisy; first plate is
   `17:00Z`, after the last known harvest). **Next on this line:** rerun `scripts/harvest_eval.py` on
   plate-bracketed harvest data, then diff/inherit auto-confirm + harvestability.
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

## Pi node — operational facts (READ before any Pi-side work)

The overhead Pi is the source of every plate. Working on capture/collapse means working on
this device — these facts are NOT obvious from the repo:

- **Access:** `pi@plantpi.local` (→ ~10.141.108.206), **key-only SSH**, user `pi`. Resolves from
  the laptop only (the Pi itself has no mDNS). Code is **flattened** at `/home/pi/plant-monitoring/`
  (`camera.py`/`capture.py` at the root, NOT under `pi/`).
- **Hardware:** ~**416 MB RAM** (~245 MB free), 4 cores (Pi Zero 2 class). `numpy` + `PIL` are
  installed; **`cv2` is NOT** (and the docker `pi` test image has neither — keep numpy/PIL imports
  inside functions). `/tmp` may be **tmpfs (RAM)** — stage large temp files on the SD card, not `/tmp`.
- **Why the burst collapse streams:** 10 full-res frames ≈ 358 MB of raw arrays — they do **not**
  fit in RAM, and staging them to SD is real flash wear. So `pi/capture.py` uses a **streaming MEAN**
  (accumulate one frame, discard it; no staging) instead of a median. This is the reason for the
  mean-vs-median choice, not preference. See the burst-plate notes in Phase 2.
- **Capture service:** runs as `pi`, hourly `plant-capture.timer`; `CAMERA=pi`, `BURST_FRAMES`
  defaults to 10. To capture a one-off burst for experiments: `ssh pi@plantpi.local`, then run a
  script with `CAMERA=pi` — never write raws to `/tmp` (tmpfs).

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

## Phase 2 — Pi monitoring: region tagging (done) + diff/inherit & harvestability (future)

> Region tagging is built and the first reference frame is tagged. The recurring payoff —
> diff/inherit + harvestability — is still to build; the Phase-1 registry seeds it.

**Region-tagging mechanism (built 2026-06-07):** reuses `photo_notes`, which already stores a
normalised rectangle (`x, y, x2, y2`, 0–1, range-checked) and ships the full draw/edit UI
(shift+drag region notes, `pendingNote`, `visualToStored()` rotation handling). A nullable
`growing_unit_id` FK was added to `photo_notes` (and `note_text` made nullable) — a region note
pointing at a unit *is* a region tag. This avoided a new `photo_regions` table. The reference
frame `2026-06-07T130010Z.jpg` now carries a human-verified set of these tags (25 units): it is
both the validation overlay and the reusable layout template. Per-region crops (reuse the
rotation-baked crop from `/photos/export`) build the per-unit dataset. AI-suggested regions
continue to live in `photo_ai_suggestions`.

**Frame registration (built 2026-06-07, `scripts/frame_registration.py`).** The geometric half of
diff/inherit. ORB features + RANSAC **partial-affine** (rigid: rotation + translation + uniform
scale — the fixed structure dominates, plants are rejected as outliers) align a frame onto the
canonical reference; `warp_region()` then projects the 25 tags (forward = target→ref for diffing;
inverse = ref→target to **inherit** a tag onto a new frame). Established empirically:

- **CLAHE light-normalisation before ORB is required** — local contrast equalisation lets matching
  survive shadow movement (e.g. 0800→1300 went unusable→solid). It is for *matching only*; it makes
  the photometric diff *worse* (amplifies shadow texture), so the change metric uses raw gray.
- **Chain through hourly hops; don't register across a big time gap directly.** A 3–4h shadow shift
  breaks ORB (the 0900→1300 direct attempt collapses to ~6 inliers / garbage transform); one-hour
  hops never do, and the small rigid transforms compose cleanly. `register_to_reference()` walks the
  chain (skip-retry bridges a weak hop) — this rescues every pair that fails direct.
- **Inlier count alone is not a trust gate.** A 303-inlier *direct* fit aligned the static top strip
  *worse* (54.8) than the chained fit (49.5); gate on inliers **and** a plausible rigid transform.
- **Drift is minor, independently confirmed** — chained 0700→1300 is rot ≈ +0.3°, ~unit scale,
  translation that scales with resolution. Consistent with "drift is not the blocker".

**The change signal is confounded by two things — foliage sway + lighting.** Geometric alignment is
solid; detecting *what changed* is not. Raw per-region absdiff is dominated by sway and lighting, not
geometric drift: even a 1-hour aligned pair shows ~50 mean-abs-diff in plant regions, and within a
single instant the leaves are in one random sway configuration. These are two distinct confounds
attacked separately: **sway is now handled at capture (below); lighting is still open.**

**Sway suppression at capture — burst-averaged plates (built 2026-06-07, `pi/capture.py`).** A single
overhead frame catches one random sway state, so single-vs-single region diff is dominated by wind, not
real change. Fix: each capture is now a **burst** collapsed to one per-pixel **plate**. Validated on
real Pi bursts (interleaved A/B = same scene, zero real change, so any residual is pure sway):

- Collapsing cut the per-region sway diff by **~60–69%**: single ≈ 16 → 10-frame plate ≈ 5.0.
- **10 frames** is the knee (5-frame floor 7.6, 10-frame 5.0, 20-frame extrapolated ~3.7); diminishing
  returns past 10, and frame count costs capture time + (for median) SD staging.
- Production uses a **10-frame streaming MEAN**, not median. Median floored slightly lower (5.01 vs the
  mean's 5.45, ~9%) but needs all frames in memory at once → on the 512 MB Pi that means staging ~358 MB
  of raw arrays to the SD card per capture (real flash wear at any non-trivial cadence). The mean
  **streams** (accumulate one frame, discard it), so nothing is staged — flash wear stays at the
  single-frame baseline (~1.6 MB/capture) at any cadence. The 9% costs little for a rough harvest read.
- The burst must span the sway **decorrelation window** (~30–50 s here; 5 *fast* frames wouldn't
  decorrelate). The per-pixel variance across the burst is a free **sway map** (which regions to distrust).
- This does **not** touch lighting — burst frames are seconds apart, same sun. Averaging cancels
  zero-mean sway; it cannot cancel the *directional* shifts of lighting or a real harvest (those would
  just blur), which is also why you can't substitute averaging adjacent **hourly** frames.

**Lighting-robust change signal — investigated 2026-06-07 (the winner: Finlayson invariant).**
Established empirically against a **known harvest** (Genovese basil ~50 g + Rocket ~50 g + Dill,
picked 17:00–18:00 CEST = the `15:00Z`→`16:00Z` frames). Three approaches A/B'd
(`scripts/lighting_experiment.py`, `finlayson_experiment.py`, `harvest_eval.py`):

- **Raw grayscale absdiff (current `region_change`) — fails.** Dominated by illumination; the
  harvested units ranked mid-pack (basil #16, rocket buried). It is lighting-sensitive *by design*.
- **ExG vegetation-coverage (2g−r−b + threshold) — fails here.** Both per-frame Otsu *and* a fixed
  threshold on normalised-rgb buried basil (#17→#8) and rocket. Root cause: the confound is illuminant
  **colour** (direct sun ~5500K vs sky-lit shadow ~10000K shifts the R:G:B ratio), and normalised-rgb
  removes **intensity**, not colour. Coverage also rose where plants caught *more* sun, masking the loss.
- **Finlayson illuminant-invariant image — works.** 2-D log-chromaticity projected onto the
  entropy-minimising invariant angle (θ, calibrated once, applied to both frames) is invariant to
  illuminant colour+intensity — exactly the confound that broke the others. On the harvest pair, abs-diff
  on the invariant (`rawINV`) ranked **rocket #1, basil #3, dill #6** of 22 (vs a no-harvest control floor
  ~10), and `gradINV` ranked basil #1. **`rawINV` (reflectance) and `gradINV` (texture) are
  complementary**: rawINV catches wispy dill (leaf→soil reflectance change, no texture), gradINV catches
  dense basil (leaf-texture thinning) — combine them.

**Two caveats the multi-pair eval exposed (`harvest_eval.py`):**
1. **Rank is not a detector — baseline is.** Absolute diff scales with region size/texture (big leafy
   regions are always loud), so the right signal is each region vs **its own** rolling baseline
   (z-score / CUSUM over many pairs), which also absorbs weather (variance) and slow pot drift. Global
   ranking leaks false positives (parsley, peppermint).
2. **The verdict needs PLATE data and isn't settled yet.** The whole 2026-06-07 series is **single,
   pre-plate frames** (burst-plate code deployed 18:41 CEST; first plate is `17:00Z`, *after* the known
   harvest). Single-frame sway inflates the baseline floor (no-harvest peaks hit 54–60 rawINV), so the
   per-region-baseline separation can't be trusted yet. The known basil/rocket harvest is stuck in the
   noisy era with **no pre-harvest plate** to diff against.

**Next:** capture a harvest **bracketed by plates** (now automatic — hourly `plant-capture.timer`, every
frame a 10-frame mean plate), then rerun `harvest_eval.py` on those de-swayed frames to settle caveat 1.
Pipeline is ready: **register → Finlayson invariant (fixed θ) → per-region rawINV+gradINV → z-score vs
per-region rolling baseline**. Then harvestability on top. (Also still ties to the open "is harvest-scale
change detectable at all?" — the −20 g evening dill remained floor-level even on the invariant, but a
larger dill pick was detected, so it is a size/resolution floor, not a blanket "no".)

### Governing principle (2026-06-07): model the per-region TIME SERIES, don't diff pairs

The decisive reframe, confirmed on real frames (basil + rocket, 2026-06-07): **a single before/after
pair is the wrong primitive.** A 50 g harvest is near-invisible cold in one noisy pair, but **obvious in
the sequence** — "flat, flat, flat, **step**, stays down". So the detector should track, **per region, a
feature value per frame** (rawINV/gradINV on the Finlayson invariant) → a **time series** → and run
**change-point / step detection** on it, not pairwise absdiff. Both confounds dissolve when you do this:

- **Sway** → averaged out at capture (burst → mean plate).
- **Lighting** → it is **predictable, not random**: it cycles **diurnally** and roughly repeats
  day-over-day. So model each region's **expected diurnal curve** (its normal value at each time-of-day)
  and treat **weather as a variance band** around that curve. An event is a **departure from the region's
  own curve**, *not* a difference from another frame. You don't fight lighting per-pair — you **predict**
  it over time and flag deviations. (This is why "compare matched time-of-day plates" was on the right
  track but too brittle: a learned diurnal baseline subsumes it and survives cloudy-vs-sunny.)

Net: **register → invariant feature per frame → per-region diurnal baseline → flag persistent departures.**
`harvest_eval.py` currently diffs consecutive *pairs* then baselines — the next iteration should track the
series directly. Build against the plate data (see Next).

### The wilt confound + water-stress monitoring (2026-06-07) — a HUGE potential win, and a trap

**Watching the same basil that "harvested" — it had only WILTED.** Midday (14:00 CEST) the exposed basil
slumped (leaves fold/droop downward, losing turgor in peak sun) and **self-recovered by ~18:00–19:00 CEST**
as the sun came off it. From overhead a wilt **looks exactly like a harvest** — both cut the projected green
canopy a naive diff sees — so a single-frame "less canopy = harvested" rule would mislabel **every midday
wilt** as a pick. This is the sharpest false-positive generator found so far.

**The time-series separates them (same principle as above):**
- **Harvest** = a step that **holds** (rocket: full at 17:00 → thinned at 18:00, stays thinned). Permanent;
  it also **reveals background** (soil / cut stems / pot rim / shade-net).
- **Wilt** = a dip that **returns** (basil: slumped at 14:00 → turgid by evening). Transient; the green
  **reorients** (leaves still there, tilted) rather than disappearing. Often **diurnal** (worst at heat peak).

Confirmed live on 2026-06-07: basil = dip-that-recovers, rocket = step-that-holds, same camera same day.

**Why this is a HUGE win if it works:** detecting wilt early is a **water-stress alert** — "go check/water
the basil" — caught hourly, before you'd notice. For fast exposed movers the wilt is recoverable same-day,
so the lead time is enough. Caveats / open problems:
- **Under- vs over-watering is NOT separable from the droop shape** (over-watering wilts too, via rotting
  roots). Don't try to auto-classify and tell the user what to do — the actions are **opposite** and a wrong
  call is fatal (watering a drowning plant). Surface it as an **attention flag**; the human diagnoses with a
  finger in the soil (10 s, the one thing vision can't do).
- The cues that *would* disambiguate are **soil-surface colour** (dry/pale vs dark/wet — directly imaged,
  but lighting-confounded and canopy-occluded) and the **wilt's recovery dynamics** (diurnal/recovers =
  under; persistent/yellowing = over). The over-watering *timely* signal is the unreliable soil one; its
  reliable signal (wilt) is **too late** (root rot already advanced). Under-watering is comfortably catchable.
- **No manual watering log** (user won't keep one — busy work, same call as the shelved harvest log).
  Watering can instead be **inferred from the camera**: a watering event = **abrupt soil-darkening** (+ a
  turgor rebound after). Needs the wet/dry soil read to be legible — **the one gating experiment** (wet soil
  is a reflectance/chroma/gloss change, not just "darker", so it *may* survive the invariant; untested).
- **Shaded plants hide thirst.** Rocket (under shade net) barely wilted at the same midday despite the same
  watering — low transpiration demand. So posture-based water-stress alerting is **biased toward exposed
  pots**; shaded ones won't telegraph and need the soil read or manual checks.

**Wilt DETECTION attempt (2026-06-08, `scripts/wilt_alert.py` — PROTOTYPE).** Tried to detect the basil
midday wilt automatically.
- **Wrong feature class first:** an appearance-distance metric (Finlayson `gradINV` to a turgid-morning ref)
  **saturated** — ~0.9 for *every* region all day, the wilt invisible. The web literature is unanimous:
  **wilt is GEOMETRY** (leaf angle / leaf-tip vertical motion / canopy droop — LAX, Kinovea, image-based
  wilting metrics), not appearance.
- **Right feature class — projected greenness/area:** a drooping canopy shows less projected green from
  overhead (folded, edge-on leaves). Green-area (ExG>thr) per region over the day **does** show it — basil
  dipped **0.85→0.71 at 12–13Z and recovered to 0.84**; shaded **rocket rose** (no wilt ✓), parsley **flat** ✓.
  So the feature class is validated where gradINV failed.
- **But single-day is not enough:** the dip is **modest (~16–20%)** and lighting/AWB/shade-net-dappling drive
  *other* regions' greenness around too — so the prototype's naive single-day rule flags the **wrong** regions
  (Rosemary, Welsh onion) and **misses** the confirmed basil. Honest prototype: feature right, rule unreliable.
- **Two real limits:** (1) **overhead is a poor angle for droop** (foreshortened) — the **closeup/LLM layer**
  sees it natively and may be wilt's proper home; (2) the cheap-metric route needs a per-region **multi-day
  diurnal baseline** (normal greenness-by-hour) to separate a real midday dip from lighting — which the
  accruing plate-days feed. Until then, treat overhead wilt as a *trigger to look*, not a detector.

### Where this is really going: a per-plant WATER-BALANCE estimator + closed-loop irrigation

The single-image under-vs-over question is the wrong frame. The right frame is a **per-plant water-balance
estimate over time**, fusing signals already (or soon) available:
- **Camera:** daily wilt/turgor curve + soil-darkening (water-stress *outcome* signal).
- **Sensors (already ingested):** temperature + humidity at the plant's actual position — the balcony has
  **two micro-climate spots**, and readings are already queryable per-photo (`GET /sensors/photos/{id}`,
  `±60 min`; see internals "Sensor proxy"). This gives **evaporative demand** at the plant.
- **Forecast (user already receives it elsewhere):** forward demand / incoming rain → ingest it.
- **Watering events:** detectable from the Flower Care soil probe — see the watering-detection note below.
  The user waters **twice a day**, and **does not always include the sensor pot**, so the probe sees an
  *irregular subset* of garden waterings (no fixed daily schedule to assume).

Fused over **days**, under-vs-over becomes tractable where a single droop is not: *daily midday wilt that
recovers after the morning water + hot/dry/no-rain* → **under** (dose < demand); *wilt that does NOT recover
after watering + soil staying wet + cool/humid* → **over** / roots. The diagnosis lives in the cross-source
correlation, not the pixels. Still surface as guidance + an attention flag, not an autonomous "do X".

**The unlock = an auto-pump (user is considering one).** It converts watering from a noisy *inferred* event
into **known ground truth: exact time + exact per-plant volume.** That dissolves the gating soil-read unknown
and turns the whole thing into a **control loop**: known input (dose) + known conditions (sensors + forecast)
→ camera measures the **output** (did wilt resolve / turgor recover) → **learn each plant's demand curve and
dose against the forecast.** Confidence in the detection is the precondition the user named for committing to
auto-pump.

**Insolation is a FIFTH input, free from the camera (lighting-as-signal duality).** The moving shadows that
*confound* change-detection are the *signal* for sun exposure: the same per-region diurnal lighting baseline
is a per-region, per-hour **insolation map** (sunlit = bright + hard shadow edge; shaded = dark/diffuse;
mean luminance per region per frame). This is the term that makes evaporative **demand per-plant** — it is
*why* the exposed basil wilted at noon and the netted rocket didn't. One modelling effort (the diurnal
baseline), two payoffs in principle: it **subtracts** lighting from the change signal AND **reads out**
insolation for the water model.

**TESTED 2026-06-07 (eve) — the NAIVE version is FALSIFIED (`scripts/insolation_experiment.py`).** Correlated
the Cilantro region's **mean 8-bit luminance** across the day's frames against the Flower Care ground-truth
`light_lux`: **Spearman = −0.43** (anti-correlated, not +1). Mean region brightness does **not** measure
insolation. Three causes, the first decisive:
1. **The camera auto-exposes.** A sunlit scene is stopped down, so a brighter-lit region does *not* read
   brighter in 8-bit — it can read the *same or darker*. Absolute luminance is not radiometric.
2. **No EXIF to correct it.** Saved frames carry **zero** exposure metadata (the burst-mean plate is
   re-encoded from a numpy array, stripping it), so auto-exposure can't be divided back out post-hoc.
3. **The lux reference is a dappled-shade point sensor** swinging ×128 hour-to-hour (612→78 489) — too
   spiky to validate against at hourly cadence regardless.

**So insolation-from-camera is not free, but not dead.** What it would take: (a) **log `ExposureTime` +
`AnalogueGain` into capture metadata** (picamera2 exposes them) — or grab one fixed-exposure "radiometric"
frame per capture — so luminance becomes meaningful; and/or (b) detect **sunlit-vs-shadow by spatial pattern**
(hard shadow edges, local contrast, specular), robust to auto-exposure, instead of mean brightness; and (c)
compare against a **smoothed sun-fraction**, not raw point lux. Until then the demand-side insolation term is
an **open build, not a freebie** — correcting the over-claim in the line above.

> **Step (a) is now BUILT (2026-06-07 eve).** `pi/camera.py` stashes the auto-chosen `ExposureTime`,
> `AnalogueGain`, `DigitalGain`, `ColourGains`, `Lux` per frame; `pi/capture.py` writes a **`camera`** block
> (last frame) + a **`burst_camera`** block (per-frame means across the plate, so "last frame representative"
> is checkable, not assumed) into the capture JSON. **Auto-exposure stays ON** (an all-day cam can't fix it —
> midday clips). Metadata failure can't break capture; `cv2`-free (numpy/PIL only). **Once redeployed to the
> Pi**, every plate carries the data to retry the radiometric insolation read AND to check AWB drift on the
> real frames. Still TODO: (b) spatial sun/shadow detection and (c) the smoothed-lux reference.

> **Validation evolution (2026-06-08, condensed):** the first plan calibrated against the Flower Care's
> overhead-visible **white cap** as a fixed-albedo co-located target — a promising n=2 morning result, then
> abandoned because the cap sits **under the shade net** (the ×128 lux swings are net sunflecks), so it reads
> dapple, not insolation. That redirected to **open-sun reference patches**, which validated:

> **VALIDATED on open-sun patches — insolation-from-camera WORKS (2026-06-08, `scripts/insolation_validate.py`).**
> Ran the revised approach on the full morning→midday arc (04–10Z = 06:00–12:00 CEST) with three open-sun
> patches (two white floor tiles + a terracotta pot rim, away from the net). **Radiometric
> `brightness/(exposure×gain)` vs the camera's whole-frame Lux: Spearman +0.96 / +1.00 / +1.00**; naive
> brightness −0.36 / +0.39 / +0.54 (flat/anti — auto-exposure compensating). The radiometric values trace the
> solar arc cleanly across the whole day, **including midday where the naive region version broke**. So the
> earlier −0.43 falsification was **purely auto-exposure + the net-dappled cilantro target**, NOT a real limit:
> with exposure logged and divided out, on a clean open-sun reference, camera brightness IS a valid insolation
> measure. **Reversal:** insolation-from-camera is **viable** (open-sun regions directly; net-shaded via the
> region-average) → the **demand-side insolation term for the water-balance model is unblocked**. Caveat: mild
> circularity — `picamLux` also derives from exposure×gain — but three independent patches agree at +0.96–1.00,
> trace the same arc, and `picamLux ≈ Flower-Care lux` in the clean morning regime, so it's corroborated, not
> tautological.

> **PER-REGION sun/shade detection WORKS via a sky-exposed REFERENCE surface (2026-06-08,
> `scripts/sun_shade.py` — PROTOTYPE).** The hard part was *per-region* sun/shade (which pot is in sun right
> now), not the global arc. Key insight: it's a **reference** problem. The cross-region average fails (it's
> contaminated by the shaded plants themselves); a **fixed sky-exposed surface not shaded by the plants**
> works — here the **glass canopy roof above the lemongrass**. Method: per region, `log(region_brightness /
> roof_brightness)` (cancels global light + auto-exposure) → per-region detrend (cancels albedo) → **+ = SUN,
> − = SHADE**. **VALIDATED against human sun/shade labels** (all local time): 09:00 chillis shade −0.63/−0.71;
> **10:00 chillis SUN +0.34/+0.44** — the dark-seedling sun-arrival that brightness-diff AND a colour-temp cue
> both *missed*; 10:00 Moroccan shade −0.03; road flips −0.22→+0.28 at 11:00 (matching "road sunny 11–15").
> Misses: parsley (partial sun), and the "car-spot" (a **moving car**, not a surface). This **reverses the
> "dark seedlings are hopeless / pause" call** — it was the reference, not the signal. **Caveats:** the
> reference must be sky-exposed & plant-unshaded; the per-region sun-map **drifts seasonally** (sun geometry)
> so it must be re-run through the year — which is exactly why **auto-detecting** beats hand-mapping once, and
> why it scales to the 100 m² garden. **Next:** per-region **sun-hours** profile (full-day arc + a few clear
> days) = the per-plant demand term; combine with the validated global arc (above).

> **SUN-HOURS profile (`scripts/sun_hours.py` — PROTOTYPE, 2026-06-08).** Integrates the per-frame sun/shade
> signal over a day's arc into per-region **sun-hours** (the demand term), multi-day averaged.
> - **Default = per-region SHADE BASELINE** (low percentile + `--margin`), NOT mean-detrend (which forces ~50% sun
>   and discards the absolute level the demand term needs). Reproduces the validated labels; needs no fixed reference.
> - **Negative-control refinement explored, then parked.** A permanent-shade control would correct the single-roof-
>   patch per-frame leak without eating real sun — sun-exposed controls and plant-cohort common-mode both *deleted*
>   the chillis' validated 10:00 sun (the dawn-shade→midday-sun sweep is real, not noise). But **no truly-fixed shade
>   surface exists in this scene** (the net dapples; thin strips are noisy; an edge strip ran 2× the dev-std →
>   `EDGE_MARGIN` guard), so the **global** control is a dead end here. Better reframe = a per-region **LOCAL**
>   reference (pot rim / bare soil by each plant): fixed, immune to the **multi-day canopy-drift** that contaminates
>   whole-region brightness. **Deferred to the multi-day build.**
> - Plumbing: region/control tags flow DB→fixture via `scripts/export_reference_regions.py` (`reference_regions.json`
>   = `regions` + `controls`; `frame_registration.load_controls()`).
> - **CHECK 2026-06-09:** rerun on the full daytime arc × accruing clear days; lock `--margin`/`--base-pct`; promote
>   per-region sun-hours into the demand term. The sun-map drifts seasonally → re-run through the year (why
>   auto-detecting beats hand-mapping once; scales to the 100 m² garden).

**Forecast source already exists** — `~/esp32-home-display/server/app/openmeteo.py` (Open-Meteo forecast +
archive), exposed at `GET /openmeteo/weather?start_ts&end_ts` on the **esp32-home-display server at
`https://laptop.local:8000/`** — the **same server the sensor proxy already reads** (`SENSOR_API_URL`; see
internals "Sensor proxy"), so ingest = another proxy/join, not a new integration. Hourly vars:
`temperature_2m, relative_humidity_2m, dew_point_2m, rain, showers, snowfall, wind_speed_10m,
wind_gusts_10m, shortwave_radiation, cloud_cover`. These are **exactly the reference-evapotranspiration
(ET₀ / Penman-Monteith) inputs** (temp, humidity, dew point, wind, solar radiation) — so per-plant water
*demand* is the **standard irrigation-scheduling computation**: ET₀ from forecast × per-plant **sun-hours
(camera)** × a crop factor. `shortwave_radiation` + `cloud_cover` are the **forecast pair** to the camera's
observed insolation → **forward** sun exposure, i.e. dose *ahead* of a hot clear day.

> **Demand side — BUILT + LIVE (`scripts/water_demand.py` + `test_water_demand.py` + `forecast_et0.py`, 2026-06-08).**
> - **VPD** (kPa) from temp+humidity alone — the immediate signal the SwitchBot sensors give per micro-climate.
>   Live: **wall ~3.6 vs railing ~2.7 kPa** → wall plants face >2× the evaporative pull, so map each region to its
>   **nearest** sensor, not a garden mean.
> - **ET₀** (FAO-56 Penman-Monteith, mm/day) from the forecast vars, full radiation chain (Ra→Rso→Rn). Validated
>   component-wise against FAO-56 published values (10/10). **Live** via `forecast_et0.py` (fetch `/openmeteo/weather`
>   → daily aggregate): **5.0–5.4 mm/day** across 06-05→08. Unit gotchas handled: wind km/h→m/s, shortwave
>   W/m²→MJ/m²/day; ea from dew point. Runs in the backend container (where `laptop.local` resolves).
> - **`plant_demand_mm` = ET₀ × Kc × camera sun-fraction** (from `sun_hours.py`) — the two halves of the model meet.
>   (Enabling fixes: `.env` `SENSOR_API_URL` :8001→:8000; esp32 openmeteo router opened to api-key auth.)
> - **Micro-climate sensors** (`SENSOR_API_URL=https://laptop.local:8000`, `X-Api-Key`): **South wall** = hot/dry by
>   the wall (highest VPD); **South** = the railing, cool & exposed (lowest VPD); **West** = where the chillis sit in
>   the **afternoon**. The esp32 server also reports an **indoor** sensor (`EC:2E:84:06:4E:9A`) that is deliberately
>   NOT in the balcony `SENSOR_SENSORS` — the config is correct, don't add it.
> - **The join — BUILT (`scripts/water_balance.py` + `test_water_balance.py`, 7/7).** Pure module:
>   `demand_mm = ET₀ × Kc × camera sun-fraction`, plus the VPD of each unit's micro-climate sensor and a
>   heat-stress flag. Runs anywhere (fed the three precomputed inputs, since they come from different
>   environments). Demo: 1.6–4.9 mm/day, chillis routed to West. **Provisional:** region→sensor map (chillis
>   34/35/36 → West afternoon, rest → South placeholder) and Kc=1.0 — no in-frame sensor positions yet.
> - **Remaining:** real region→sensor positions; per-species Kc; the live orchestration gluing host `sun_hours`
>   + container `forecast_et0`/VPD into the join's inputs; the multi-day sun-hours profile.

**Ground-truth calibration anchor: a Xiaomi Flower Care in the Cilantro pot.** One pot already has a soil
probe (sensor `Cilantro`, type `xiaomi`, id `3ee7f8a3-9811-45ce-8296-c909a104952b`, on the same esp32 server;
`GET /sensors/{id}/readings`, ~every 3 h). Four channels: **`moisture_pct`, `light_lux`, `temperature_c`,
`conductivity_us_cm`** (EC/fertility). This is the **hard ground truth** for the two things the camera can only
*infer*:
- **`moisture_pct` = the real "I watered" signal + dry-down curve + under/over level.** Observed 2026-06-07:
  25→25→28→29→29→**33**→33 across the day — a clear watering step, where soil-darkening only guesses.
- **`light_lux` = ground-truth insolation at that pot** (e.g. ~54k lux dawn peak, low/diffuse midday) to
  calibrate the camera's per-region luminance→sun-hours read.

**The leverage: one sensor bootstraps the whole camera model.** You don't need a probe per pot — learn the
**camera→moisture** (soil-darkening) and **camera→insolation** (per-region luminance) mappings *on the Cilantro
pot, where there's truth*, validate against the Flower Care, then **transfer the calibrated vision read to the
sensorless pots.** A single ~$15 sensor turns the gating "is wet/dry soil legible?" unknown into a supervised
calibration problem. (`conductivity` is a bonus nutrient/feeding signal.)

**Watering detection from the probe — FUSE conductivity + moisture, not either alone (2026-06-08,
`scripts/watering_detector.py`).** Validated over 19 days of Cilantro history. A watering shows up as a sharp
**disturbance**, but on *different channels on different days*:
- **EC step UP** = feed, or water flushing accumulated salts past the electrodes in dry soil;
- **EC step DOWN** = plain/low-ion water **diluting** the soil solution — so the EC *sign* is information
  (feed vs plain water), not noise;
- **moisture step up** = water wetting the capacitive shaft — coarse, laggy, integer %, **least reliable**
  (pinned for hours; missed a *confirmed* watering on 06-08), but occasionally carries an event EC misses (06-01).
Single-channel misses a large fraction; the fused "soil-disturbance" detector catches ~all. Detector trick:
a **short (2-reading) baseline** so it tracks the slow post-feed EC decay and only triggers on a *sharp*
change (a long baseline misfired on every decay step as a bogus dilution); plus a refractory so one
disturbance = one event. **Scope/limits:** the probe is **one pot only** and the user waters **twice daily
without always including it**, so events are an irregular subset — the probe is the **ground-truth anchor**;
the **camera (soil-darkening)** is what generalizes watering detection to the sensorless pots. Thresholds are
**provisional** pending a few human-labelled waterings (decay-rejection is the main remaining tuning). One
label so far: 06-08 watering before 08:00 SAST → detector flagged `06:03Z EC+359`. ✓

**Later feature (deferred): EC as a fertility/nutrient signal.** Beyond watering *events*, the conductivity
**baseline between waterings** tracks the soil's dissolved-nutrient load, and the EC-step *sign* hints feed
vs plain water. Over time that's a per-pot **feeding/fertility** signal (when to feed, EC drawn down by uptake,
salt buildup). Not now — needs the watering detector solid + labelled feeds first; recorded so it isn't lost.
**Why it matters beyond the balcony:** this is the prototype for a planned **~100 m² garden next year**, where
automated irrigation is the crucial scaling lever — manual watering doesn't scale; a **sense → dose →
measure-response → adjust** loop does. The balcony water-balance work is that loop in miniature.

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
5. ✅ **Region tagging** (2026-06-07) — `photo_notes.growing_unit_id` FK + nullable `note_text`
   (migration `0013`); region-tag UI (shift-drag a box → growing-unit dropdown → unit name
   renders on the box; a note can be unit-only, text-only, or both). Reference frame
   `2026-06-07T130010Z.jpg` tagged with all 25 units. E2E + unit coverage added.
6. ⚠️ `scripts/prepare_tagging_run.py` — built, but its **256px contact-sheet grid is
   superseded** (see Appendix B). Reuse only its session-grouping; switch transport to
   per-image Batch API.
7. ✅ **Frame registration** (2026-06-07, `scripts/frame_registration.py`) — CLAHE + chained-hop
   ORB alignment, `warp_region()` tag inheritance, per-region diff. Tested standalone
   (`scripts/test_frame_registration.py`; cv2 isn't in the backend image) with synthetic
   algorithmic tests + real-frame tests against committed downscaled fixtures
   (`scripts/testdata/frames/`). The geometric half of diff/inherit; see Phase 2.
8. ✅ **Burst-averaged plates** (2026-06-07, `pi/capture.py`) — each capture is now a 10-frame
   burst collapsed to a streaming-MEAN plate on the Pi, cutting per-region foliage sway ~60–69%
   (validated on real bursts). Streams (no SD staging → baseline flash wear); numpy+PIL only.
   `scripts/sway_experiment.py` is the isolated validation tool (synthetic + on-Pi capture +
   analyze). Suppresses the *sway* half of the change-signal confound; lighting still open.

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
- **Phase 2**: frame registration ✅ + burst plates ✅ + lighting-robust signal ✅ (Finlayson invariant) +
  **time-series harvest/wilt detector ✅ built & validated** (`scripts/harvest_eval.py`, see below).
  Remaining: rerun on **plate-bracketed** harvest data (cleaner than the pre-plate frames it was validated on),
  then diff/inherit auto-confirm + harvestability.

  > **`harvest_eval.py` is now the time-series detector (2026-06-08).** Per region, per frame: Finlayson-
  > invariant distance to the reference (one θ for the series) → **common-mode detrend** (subtract the
  > per-frame median across regions = the shared diurnal lighting, so each region's *idiosyncratic* change
  > remains) → **tail-run persistence**: an elevation that **holds to the end** = harvest; one that **returns**
  > = wilt. Validated on the known 2026-06-07 harvest (single, pre-plate frames): **Genovese basil (10.5) and
  > Rocket (5.9) correctly flagged harvest at 16Z**, controls clean, and the **wilt-vs-harvest confound
  > resolved** (basil called harvest, not wilt, despite also wilting at midday). **Dill borderline** (real
  > signal `…5 6` but only 1 frame clears 3σ — wispy/small; plates should clear it). `k_sigma` (default 3) is
  > the tunable; left conservative rather than overtuned on one noisy day. Supersedes the old pairwise diff.

- **Water-balance demand side ✅ built & LIVE** (2026-06-08): insolation-from-camera validated
  (`insolation_validate.py`); per-region **sun-hours** profiler (`sun_hours.py`); **VPD + FAO-56 ET₀**
  (`water_demand.py`, 10/10 FAO-validated) running on the **live** forecast (`forecast_et0.py`) and sensor proxy;
  region/control tag export (`export_reference_regions.py`). Supply side: watering detection ✅
  (`watering_detector.py`), auto-pump TBD; wilt detection prototype (`wilt_alert.py`) — greenness is the right
  feature, needs a multi-day diurnal baseline. **Per-plant join ✅ built** (`water_balance.py` + test); remaining:
  real region→sensor positions + per-species Kc + the live orchestration (host `sun_hours` + container
  `forecast_et0`/VPD), and the multi-day sun-hours profile.

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

### 2026-06-07 (eve) — lighting-robust change signal: Finlayson invariant wins
Tested against a **known harvest** (Genovese basil ~50 g + Rocket ~50 g + Dill, picked 17:00–18:00
CEST = `15:00Z`→`16:00Z`). Walked three methods; see Phase 2 "Lighting-robust change signal" for the
full write-up and the three scripts. Short version:
- **Raw absdiff** and **ExG vegetation-coverage** both **failed** — harvested units buried mid-pack.
  ExG failed even on normalised-rgb + fixed threshold because the confound is illuminant **colour**
  (sun ~5500K vs sky-lit shadow ~10000K), and normalised-rgb only removes intensity.
- **Finlayson illuminant-invariant image won:** `rawINV` ranked rocket #1 / basil #3 / dill #6 of 22
  (no-harvest floor ~10); rawINV (reflectance) + gradINV (texture) are **complementary** (dill needs
  rawINV, basil needs gradINV).
- **Two caveats:** (1) rank≠detector — use a **per-region rolling baseline** (z-score/CUSUM), which also
  absorbs weather and pot drift; (2) **not settled** — the entire series is **pre-plate single frames**
  (plate code deployed 18:41 CEST; first plate `17:00Z`, *after* the harvest), so sway inflates the
  floor (no-harvest peaks 54–60). **No pre-harvest plate exists** for this event.
- **Pi confirmed capturing plates** from `17:00Z` on (`pi@plantpi.local`, hourly `plant-capture.timer`,
  `BURST_FRAMES=10`, metadata `derived_plate:true`). Verdict awaits a **plate-bracketed** harvest, then
  rerun `harvest_eval.py`. (The −20 g 06-06 evening dill stayed floor-level even on the invariant — a
  size/resolution floor for wispy foliage, not a blanket "undetectable".)
