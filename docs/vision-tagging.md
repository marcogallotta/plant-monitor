# AI / Vision Tagging — photo-to-unit support layer

_Status: active working design. This draft replaces the old research-diary shape with a current
spec + durable lessons._

This doc owns the **image-to-growing-unit tagging layer** across:

- fixed Pi overhead frames
- historical phone/camera photos
- future requested manual photos
- closeups used for cooking and plant condition reads

It supports:

- plant identity and region mapping
- confirmed photo → growing-unit links
- reference corpus building
- cooking availability reads
- harvest / move / died-back / replanted change events
- irrigation context: crop identity, crop stage, canopy cover, sun/shade, zone state

It does **not** own:

- irrigation control, sparse-probe calibration, pump dosing, or water-balance equations — see
  [`irrigation.md`](irrigation.md)
- nursery strategy, crop prioritisation, or scaling thesis — see [`nursery.md`](nursery.md)
- generic image-processing experimentation unless it produces one of the outputs above

## Core thesis

The vision problem is not "identify plants from pixels".

The useful problem is:

> turn messy images into confirmed links between photos, growing units, regions, crop state, and
> practical actions.

The Pi gives a stable overhead anchor. Phone/camera photos give detail. Future requested manual
photos are how this scales when fixed cameras are not enough.

The whole layer exists to connect those image streams into reliable, reviewable plant context.

## Image streams

| Stream                              | Role                                                               | Main value                     | Main weakness                                               |
| ----------------------------------- | ------------------------------------------------------------------ | ------------------------------ | ----------------------------------------------------------- |
| **Pi overhead**                     | stable map, identity-by-position, change hints, sun/canopy context | continuous, comparable, cheap  | low detail; confusables and harvest amounts often invisible |
| **Historical phone/camera archive** | reference corpus, closeups, past growth/condition examples         | high detail; real examples     | hard to tag reliably; current blocker                       |
| **Future requested manual photos**  | scalable context when fixed cameras do not cover a bed/site        | targeted, cheap, human-in-loop | only useful if tagging can map photo → unit/zone/state      |
| **Closeups**                        | condition, harvestability, discriminating identity features        | best value reads               | sparse and must be linked to the right unit                 |

Non-Pi image tagging is not optional backfill. It is the bridge between the current balcony system
and a scalable garden/greenhouse workflow.

## Current state

### Built / validated

- `photo_ai_suggestions` table and review workflow exist.
- `photo_growing_units` stores confirmed photo → growing-unit links.
- `reference`-labelled confirmed photos are the curated reference pool.
- Region tagging is built using `photo_notes.growing_unit_id`.
- Reference frame `2026-06-07T130010Z.jpg` is human-tagged with 25 units.
- Frame registration exists in `scripts/frame_registration.py`.
- Pi burst-averaged plates are built in `pi/capture.py`.
- Sway suppression from burst mean reduced foliage sway noise by roughly 60–69%.
- Finlayson illuminant-invariant signal was method-found for lighting-robust change, but needs
  plate-bracketed harvest validation.
- Closeups are validated as the value layer for identity/condition where overhead is weak.

### Still unresolved

- Reliable tagging of historical non-Pi phone/camera photos.
- Frictionless phone/camera import/sync.
- Agreement-gated Batch API workflow for archive recovery.
- Turning confirmed non-Pi images into a clean reference corpus.
- Future manual-photo workflow: request photo → identify bed/unit → extract
  crop/canopy/stage/condition.
- Plate-bracketed validation for harvest/change detection.
- Clear review policy for confusables and seedlings.

## Current build order

1. Keep the Pi region map authoritative.
2. Make phone/camera import frictionless.
3. Fix non-Pi photo-to-unit tagging on a small validation set before running the full archive.
4. Build a confirmed reference corpus from accepted non-Pi closeups.
5. Use tagged closeups for cooking availability and plant condition reads.
6. Export irrigation context where useful: sun/shade, canopy bucket, crop stage,
   moved/harvested/died-back.
7. Use Pi frames for continuity, region-map maintenance, gross change, sun/canopy context.
8. Run large historical archive recovery only after the small tagging validation stops failing.

Do not spend another session improving generic image recognition. The key blocker is photo-to-unit
tagging with the right priors and review loop.

## Non-Pi tagging problem

### Why it matters

The historical phone/camera archive likely contains the best available data for:

- closeup identity features
- crop stage
- harvestable condition
- plant health / stress examples
- canopy development
- human photo-taking patterns
- training/evaluation for future requested manual photos

A fixed Pi camera will not give enough detail and will not scale across larger plots or multiple
sites. If manual requested photos are part of the future irrigation/cooking loop, the system must
learn to tag non-Pi photos reliably.

### Status

Paused, not abandoned.

Past attempts failed badly, but that does not prove the task is impossible. It proves the old setup
was wrong.

### Known failed approach

Do not rebuild:

- 256px contact-sheet grid
- cheap model
- open-world "what plant is this?"
- self-reported confidence as the acceptance gate
- grid-cell photo-ID mapping as a trusted transport
- no current inventory/date/state prior

A live run produced about 44% precision even on the model's own high-confidence tier. It overused
lemongrass as a catch-all, confused sage/basil, tagged fringe plants, and may have associated
answers with the wrong grid cells.

## Suspected smoking guns

Past failures probably came from these issues, not from the goal being impossible:

1. **Resolution starvation.** 256px contact sheets turned useful plant detail into green blobs. Use
   individual images at 1024px or better where possible.

2. **Grid/cell ID misassociation.** Contact sheets introduced a transport bug class: the model may
   describe the wrong cell/photo ID. Use one image per request for serious tagging runs.

3. **Open-world identification.** The model was asked to identify plants in general instead of
   matching against this project's live closed set.

4. **No first-class photo date.** Date matters. A plant that did not exist yet, was still seedlings,
   or had already died cannot be the answer.

5. **No current inventory state.** Stage, size, pot, count, status, and confusable group need to be
   fed before leaf-shape guessing.

6. **Weak container/composition priors.** Troughs and pots have composition signatures.
   Container-first matching often beats plant-level botany.

7. **Long/stale prose priors.** A rich prior can help, but long stale prose can make the model
   hallucinate expected compositions. Use compact matrices/state, not essays.

8. **Self-confidence was trusted.** Model confidence was anti-calibrated on confusables. Agreement
   and review are the gates, not self-confidence.

9. **Confusables were forced into single labels.** Chilli varieties, alliums, basil variants,
   parsley/cilantro, thyme/lemon thyme, and mint variants need options unless position/date/state
   pins them.

10. **Seedlings were over-labelled.** `SEEDLINGS` is a valid known-unknown. It should be upgraded
    later, not forced now.

11. **Review loop may be the bottleneck.** The system needs cheap human review of disagreements, not
    blind auto-acceptance.

## Next validation test for non-Pi tagging

Before running the full archive, do a small A/B validation.

### Sample

30–50 photos from the historical phone/camera archive, deliberately mixed:

- clear single-subject closeups
- multi-plant trough shots
- partial edge/fringe photos
- seedlings/trays
- confusable groups
- dated photos where current state rules out some candidates
- a few known bad cases from the failed run

### A/B prompts

Run two versions:

1. **Thin prior:** closed set + schema only.
2. **Rich compact prior:** closed set + photo date + inventory state + container/composition
   matrix + confusable rules.

Do not use long narrative priors.

### Success criteria

The rich prior should reduce wrong confident singles and reduce human review time. It should not
force stale expected compositions when the photo visibly disagrees.

Track:

- correct accepted single labels
- correct options on confusables
- overconfident wrong singles
- hallucinated expected plants
- missed secondary/fringe regions
- review time per photo
- whether date/state priors actually changed wrong pixel-based guesses

## Priors-first tagging model

Identity comes from priors first. Vision confirms and reads condition.

Priority order:

1. **Photo date** What existed, what was seedling-stage, what was dead/retired, what had moved?

2. **Live growing-unit state** Stage, size, count, status, pot/container, known confusables.

3. **Container / composition** Trough or pot identity, known plant groupings, relative arrangement.

4. **Region / position** For Pi frames and photos that can be mapped to the layout, position is
   stronger than pixels.

5. **Reference corpus** Confirmed reference images for the candidate unit or confusable group.

6. **Visual features** Leaf shape, texture, stem, colour, growth habit, scale, condition.

7. **Agreement gate** Trust cross-read agreement and human review, not model self-confidence.

## Closed set and confusable policy

The closed set comes from the live DB and `plants-data.md`, not from stale prose. Verify before
running a batch.

### Distinctive enough for confident singles when clearly visible

- dill
- parsley
- rocket
- rosemary
- sage
- sorrel
- French tarragon
- mature lemongrass
- mature basil when the unit/context is pinned
- mature mint when the unit/context is pinned

### Confusable groups: use options unless context pins the answer

- peppermint / Moroccan mint
- chives / garlic chives / Welsh onion
- parsley / cilantro
- Genovese basil / Thai basil / Thai basil vendita
- bird's-eye chilli / Hangjiao H7 / Hangjiao H4
- lemongrass / rau ram
- sorrel / rau ram
- thyme / lemon thyme

Rules:

- Pixel-identical varieties are never vision-only calls.
- If the answer depends on exact cultivar/variety, use position, pot, date, or DB state.
- If still uncertain, output options and send to review.
- Do not reward the model for a confident single pick on a known confusable.

### Seedlings ladder

Never force a species onto ambiguous seedlings.

- **low confidence:** `SEEDLINGS`
- **medium confidence:** group/options, e.g. `apiaceae seedlings`, `allium seedlings`,
  `basil/chilli seedling`
- **high confidence:** exact species only if leaves are genuinely clear or date/container/state pins
  it

A `SEEDLINGS` tag is a known-unknown. It can be upgraded later by growth, clearer photos, or
container state.

## Tagging units

### Troughs

Use container-first matching.

A trough photo should usually output one row per visible plant/zone, but the identity logic should
start with the container/composition signature.

Do not ID each leaf as if it were an independent wild plant.

### Round pots

Usually plant-level ID.

Single-subject pot photos are the easiest source of reference images, but confusables still need
options when the pot/unit is not pinned.

### Trays / seedlings

Use the seedlings ladder. Do not over-label.

### Pi overhead regions

Identity mostly comes from the region map, not appearance. Vision reads presence/change/coverage
more than species.

### Manual requested photos

The question is usually not "what species is this?" but:

- which bed/zone/tray/unit is this?
- what crop or crop mix is present?
- what canopy/stage bucket is it in?
- has anything changed: moved, harvested, died back, replanted?
- is there a useful condition/harvestability observation?

## Reference corpus

Confirmed links live in `photo_growing_units`.

The curated high-quality subset carries the `reference` label.

A good reference image is not just pretty or sharp. It clearly shows discriminating features for a
unit or confusable group.

Examples of useful reference qualities:

- lemongrass red base / wide blades / midrib / pot scale
- garlic chives vs chives relative thickness/stage
- basil variety only when linked to unit/pot/date
- rau ram vs sorrel habit/leaf detail
- thyme vs lemon thyme only if container/unit pins it
- mature vs seedling state for the same crop

Rules:

- Reference corpus is confirmed-only.
- Do not let guesses into the reference set.
- Prefer images that are both high-quality identity references and recent state references, but keep
  those two roles distinct.
- Old reference images can remain useful for identity even when stale for harvestability.
- Recent images are useful for state even if not ideal as identity references.

## Two-axis retrieval

Every image can be useful in two different ways.

### Identity / disambiguation

Use the best confirmed references for the unit or confusable group. Age matters less if the features
are durable.

### State / harvestability

Use the most recent images, weighted by plant growth speed and microclimate.

Fast crops go stale quickly: rocket, basil, dill, cilantro, leafy succession crops.

Slow woody herbs stay useful longer: rosemary, sage, thyme, tarragon.

The system should combine both:

- reference-labelled confirmed shots for identity
- recent shots for state
- Pi overhead for gross freshness and change

## Pi overhead layer

The Pi overhead stream is an index and continuity layer.

It is good for:

- fixed layout map
- identity-by-position
- region presence
- gross change
- move/change hints
- sun/shade / exposure context
- canopy coverage trends
- keeping recent closeups honest

It is weak for:

- fine ID among confusables
- visually identical varieties
- precise harvest amounts
- small harvest changes
- subtle condition reads

A known roughly 20 g dill harvest was invisible from overhead. That is a design fact, not a
temporary bug.

### Region map

The reference frame `2026-06-07T130010Z.jpg` is the current authoritative Pi layout snapshot.

Region tagging is implemented by `photo_notes.growing_unit_id` with normalised rectangles.

The region map is stronger than visual species recognition for:

- lemongrass vs garlic chives
- chilli varieties
- visually identical varieties
- repeated pots/troughs whose identity is known by position

### Frame registration

`scripts/frame_registration.py` handles geometric inheritance of regions.

Known findings:

- CLAHE helps ORB matching survive lighting shifts.
- CLAHE is for matching only; it worsens photometric diff.
- Chain through hourly hops; direct long-gap registration can fail under shadow shifts.
- Inlier count alone is not a trust gate.
- Gate on inliers plus plausible rigid transform.
- Drift is minor; it was not the main blocker.

### Burst plates

`pi/capture.py` captures a burst and collapses it to a streaming mean plate.

Reason: Pi memory and SD wear.

Do not replace with median unless the memory/storage tradeoff is explicitly solved.

## Camera-derived irrigation context

Irrigation control does not depend on continuous camera observation. See `irrigation.md`.

This layer can still provide irrigation context:

- static or slow-changing sun exposure / insolation map
- canopy cover bucket
- crop stage
- crop identity / Kc context
- major state changes: moved, harvested, died back, newly sown
- manual requested photo interpretation

Coarse canopy/stage buckets are enough:

- bare / newly sown
- seedlings
- sparse canopy
- moderate canopy
- heavy canopy

The output should be context and confidence, not an irrigation command.

## Cooking availability / condition reads

The original product is still useful:

> what is cookable right now, roughly how much, and in what condition?

This is mainly a closeup/manual-photo task, supported by Pi freshness.

Useful outputs:

- plant/unit identity
- harvestable/not harvestable
- rough relative amount
- condition: flowering, bolting, wilting, yellowing, pest damage, drought stress, recovering,
  vigorous
- freshness/staleness date
- suggested urgency: use now / wait / check again / likely stale

Do not require gram-accurate logging. Rough usable amounts are enough for cooking.

Asana/harvest notes should not be a required operating dependency. Occasional human/cooking
corrections can still provide calibration evidence.

## Change detection lessons

### General rule

Model the per-region time series. Do not trust pairwise diffs alone.

Lighting, watering, wind, and camera changes create common-mode shifts. The useful signal is often a
region changing relative to its own baseline and relative to other regions.

### Common-mode trap

Common-mode detrending can erase real synchronous events.

If multiple plants are harvested or watered together, treating that as lighting noise can remove the
event.

Use common-mode correction carefully. Preserve the possibility of real group events.

### Harvest

Overhead may miss small harvests. Higher resolution and closeups/manual photos are likely better for
harvest amount.

Pi overhead can still detect large visible changes and keep stale closeups honest.

### Wilt / water stress

Wilt is geometry more than appearance.

The failed path: appearance-distance / invariant colour metrics saturated and missed confirmed wilt.

The more promising cheap signal: projected green area per region can drop when leaves droop, but
single-day rules are unreliable because lighting and shade move other regions too.

Treat overhead wilt as an attention flag, not a diagnosis.

Under- vs over-watering is not separable from droop shape alone. Over-watering can wilt too.
Diagnosis belongs in irrigation data, soil/probe response, weather, and human inspection.

### Move detection

Do not rely on one visual feature.

Moves can look like lighting, growth, harvest, sway, or partial occlusion. Use region map,
registration, continuity, and human confirmation.

## Batch API / archive recovery plan

This is paused, not abandoned.

Purpose:

1. recover the historical phone/camera archive into confirmed photo → unit links
2. build the reference corpus
3. prove the workflow needed for future requested manual photos

### Transport

Use individual images, not contact sheets.

- one image per request
- 1024px or better where practical
- compact cached system prompt
- structured JSON output
- run ID / batch ID stamped on suggestions
- no interactive Claude reads for production-scale archive tagging

### Model gate

Proposed production flow:

1. Sonnet pass on all selected images.
2. Auto-accept only safe distinctive singles with strong context agreement.
3. Send options/confusables/low-confidence/seedlings to a second model pass or review.
4. Use Opus or a second independent read on the flagged subset.
5. Accept only when reads agree and priors are consistent.
6. Human reviews disagreements and corrections.

Costs and current Batch API pricing should be verified before any large run.

### Prompt principles

The prompt must say:

- closed-set match, do not free-guess
- photo date is first-class
- inventory state is first-class
- use container/composition as hints, not facts
- if visible evidence contradicts the prior, say so
- output one object per visible plant/zone
- scan edges for fringe plants
- confusables require options
- seedlings use the ladder
- confidence is not an acceptance gate

Keep priors compact: tables/matrices/state, not long prose.

## DB / surfaces

### Existing / intended core tables

`photo_ai_suggestions` stores one suggestion per image region.

Important fields:

- `photo_id`
- `model`
- `batch_hint`
- `prompt_context`
- `x, y, x2, y2`
- `suggested_plant_id`
- `suggested_plant_name`
- `suggested_photo_type`
- `suggested_rotation`
- `suggested_labels`
- `suggested_options`
- `confidence`
- `question`
- `observation`
- `status`
- `edited_plant_id`
- `edited_photo_type`
- `edited_labels`
- `created_at`
- `reviewed_at`

`photo_growing_units` stores confirmed photo → unit links.

`photo_labels` stores labels such as `reference`.

`photo_notes.growing_unit_id` stores region tags on Pi/reference frames.

### Review UI needs

- ingest suggestions
- list pending suggestions
- show full image and region crop
- accept / edit / reject / delete
- choose from `suggested_options`
- write accepted links to `photo_growing_units`
- apply labels, especially `reference`
- support keyboard review
- protect against duplicate ingest

### Outstanding schema/workflow improvements

- explicit `run_id` and `batch_id` columns
- duplicate-ingest protection
- container/composition registry as first-class data
- session-propagation actions for human-reviewed groups
- mobile-friendly review for manual-photo workflows

## Pi operational facts

Read before Pi-side work.

- Access: `pi@plantpi.local`
- Code is flattened at `/home/pi/plant-monitoring/`
- Do not assume files are under a `pi/` subdirectory on the device.
- Hardware is Pi Zero 2 class, around 416 MB RAM.
- `numpy` and `PIL` are available.
- `cv2` is not installed on the Pi.
- Docker test image may also lack `cv2`.
- Keep numpy/PIL imports inside functions when needed.
- `/tmp` may be tmpfs/RAM; do not stage large raw frames there.
- `plant-capture.timer` runs hourly as `pi`.
- `CAMERA=pi`.
- `BURST_FRAMES` defaults to 10.
- Burst collapse uses streaming mean to avoid holding all frames in RAM and avoid SD staging/wear.

## Do not re-open these traps

- Do not rebuild the 256px contact-sheet grid pipeline.
- Do not treat self-confidence as a trust gate.
- Do not ask open-world plant ID when this is a closed-set matching problem.
- Do not ignore photo date and live inventory state.
- Do not force confusables into confident single labels.
- Do not force species onto ambiguous seedlings.
- Do not let guessed links into the reference corpus.
- Do not make Pi overhead responsible for fine identity or precise harvest amounts.
- Do not make irrigation depend on continuous camera reads.
- Do not turn occasional human corrections into required manual logs.
- Do not bury durable lessons inside chronological narration.

## Open questions

- What exactly is the photo mix of the historical archive: closeups, troughs, wide overviews,
  seedlings, edge cases?
- Which 30–50 photos should form the first A/B validation set?
- What compact inventory-state format best prevents pixels-over-priors mistakes?
- What is the minimum review UI needed to make non-Pi tagging tolerable?
- When should a photo become a `reference` image?
- Should future requested photos be linked to capture requests / tasks?
- What are the per-species harvestability thresholds?
- Can plate-bracketed Pi data validate harvest/change detection, or should harvestability live
  mostly in closeups?
- How should stale closeups decay by plant type and microclimate?

## Appendix A — durable evidence summary

### 2026-05-31 failure

256px contact-sheet grid + cheap model + open-world ID + self-confidence gate failed badly.

Main observed failures:

- low precision despite high confidence
- lemongrass over-predicted as catch-all
- sage misread as basil
- fringe plants tagged incorrectly
- possible photo-ID/grid-cell misassociation

Conclusion: grid is dead.

### Resolution ladder

- 256px: green blobs
- 512px: dominant plant type sometimes visible
- 1024px: more variety/detail/condition
- visually identical varieties still cannot be solved from pixels alone

Conclusion: use adequate resolution, but do not expect pixels to solve variety identity without
priors.

### Priors-first validation

A later held-out read suggested the task is feasible when date/state/position/count/pot priors are
used first.

Distinctive plants performed well. The decisive lemongrass ↔ garlic-chives failure did not recur
when the model had the right relational priors.

Every observed miss was a pixels-over-priors miss.

Conclusion: the pipeline must rule out candidates by date/state/context before leaf-shape voting.

### Pi region marking

Reference frame tagging became load-bearing because vision confidently swaps confusables and cannot
separate pixel-identical varieties.

Conclusion: region map is authoritative for Pi identity.

### Closeups

Closeups are the value layer for:

- discriminating features
- condition
- harvestability
- reference corpus

Conclusion: make phone/camera import easy and make non-Pi tagging reliable.

### Frame registration / change signal

- CLAHE helps ORB matching.
- Chained hourly hops beat direct large-gap registration.
- Foliage sway is a major confound; burst mean helps.
- Lighting remains a major confound.
- Finlayson invariant is promising but needs validation on plate-bracketed events.

Conclusion: Pi change detection is useful but must be time-series-based and conservative.

## Appendix B — old content policy

The previous `ai-tagging-design.md` contained valuable research narration. Keep old chronological
detail only as evidence, not current instruction.

Current sections win over old appendices when they conflict.

Future additions should follow this rule:

- put current decisions and build order near the top
- put durable failure lessons in `Do not re-open these traps`
- put long experiment narration in an appendix
- move irrigation model/control material to `irrigation.md`
- move nursery strategy to `nursery.md`
