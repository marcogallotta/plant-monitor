# Edible Plant Nursery Automation Roadmap

_Status: current execution roadmap. This is the navigational entry point for the project docs._

This project is now oriented around a practical goal:

> Build a sparse, calibrated irrigation + plant-context system that lets a one-person, quality-led
> edible-plant project scale from balcony to garden without drowning in daily watering labour.

## Project docs

| Track                                 | Doc                                      | Owns                                                                                    |
| ------------------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------- |
| **A — Irrigation control**            | [`irrigation.md`](irrigation.md)         | water-balance model, sparse probes, pump dosing, EC/moisture response, safety           |
| **B — Photo-to-unit tagging**         | [`vision-tagging.md`](vision-tagging.md) | Pi frames, phone/camera archive, manual-photo tagging, reference corpus, vision context |
| **C — Nursery direction**             | [`nursery.md`](nursery.md)               | crop priorities, scaling context, strategy, operating constraints                       |
| **D — Platform / import / review UX** | code + operational docs                  | the boring infrastructure: import, sync, review, IDs, data integrity                    |

## Current north star

The primary product is **sparse calibrated irrigation**.

The supporting layer is **photo-to-unit tagging**: turning Pi frames, phone/camera photos, and
future requested manual photos into reliable plant/unit/context data.

The nursery strategy supplies the reason this matters: watering scales badly with plant count,
warm-tender quality crops are the moat, and manual logs are not the operating model.

## Working principles

### Irrigation first

Watering is daily, non-deferrable, and scales with plant count. It is the main bottleneck to moving
beyond the balcony.

### Known-input dosing is the next unlock

Human watering is noisy and inferred. Pump dosing turns watering into a measured input:

```text
sense → dose → measure response → adjust
```

### Sparse sensing is the economic trick

Probes should calibrate soil/zone behaviour, not continuously sense every plant.

A few probes should anchor many zones through weather, forecast, sun-map, canopy state, known
dosing, and learned coefficients.

### Camera is context, not the core irrigation sensor

Camera/tagging can provide sun exposure, canopy cover, crop stage, identity, and change events.

It should not be required for basic watering control.

### Non-Pi tagging is central

The phone/camera archive is not optional backfill. It is the likely source of the best closeups,
reference images, growth-stage examples, and validation data for future requested manual photos.

### No manual-log dependency

Occasional human corrections are useful. Routine manual logging must not be required for the system
to work.

## Phase 0 — Preserve the working baseline

Do not break the parts that already work.

Keep stable:

- Pi capture
- hourly burst-averaged plates
- sensor ingestion
- weather / forecast feed
- ET₀ / VPD demand model
- Flower Care EC + moisture probe data
- current watering-event detection
- region map / reference frame
- existing photo review workflow
- confirmed photo → growing-unit links
- reference-labelled photos

This is the base the next phases build on.

## Parallel workstreams

The roadmap is phased, but not everything is strictly blocked by hardware.

### Hardware-gated

These need pump/valve hardware:

- known-input dosing
- measured dose-response curves
- pump/valve safety testing
- bounded auto-dosing
- zone-level closed-loop control

### Software-only / can continue now

These can sharpen while pump hardware is sourced:

- improve passive drydown model
- add or test `Ks(moisture)` from natural drydown curves
- wire in coarse canopy term
- refine sun-map / insolation context
- gather more probe days
- validate VPD / ET₀ / moisture / EC relationships over more weather cycles
- clean non-Pi photo import
- run small A/B tagging validation
- build review workflow improvements

Do not let the lack of pump hardware stall the entire roadmap. The dose-response half needs the
pump; the passive-drydown-model half does not.

## Phase 1 — Known-input irrigation

Goal: replace inferred human watering with measured pump dosing.

Tasks:

- choose initial pump/valve architecture
- define zones
- record dose events cleanly:
  - zone
  - time
  - volume or duration
  - pump/valve state
  - source water if relevant
- measure EC + moisture response after known doses
- add basic safety limits:
  - max dose per cycle
  - cooldown between repeated doses
  - fail closed on unknown state
  - conservative handling of sensor outliers
- keep human in the loop at first

Success criterion:

> The system can apply a known dose and observe a usable EC/moisture response without depending on
> manual watering inference.

## Phase 1b — Passive model sharpening

Can run before or alongside pump work.

Goal: improve the depletion side of the model using existing sensors and natural drydown.

Tasks:

- gather more Flower Care drydown segments
- compare VPD, ET₀, temperature, sun exposure, and drydown
- test `Ks(moisture)` from natural drydown slowdown
- add coarse canopy/crop-stage multiplier
- separate sensor noise from real drydown
- document which coefficients are pot-specific and non-portable
- avoid overfitting one cilantro pot

Success criterion:

> The model predicts relative drydown pressure better than simple ET₀/VPD alone, while clearly
> marking what is only balcony-pot calibration.

## Phase 2 — Sparse calibration

Goal: prove the scaling architecture.

Tasks:

- use one/few probes as calibration anchors
- fit per-zone or per-soil coefficients from drydown and dose response
- reuse coefficients across similar zones
- define when recalibration is required:
  - new soil
  - pot → ground
  - season change
  - crop density change
  - irrigation hardware change
- avoid one-probe-per-plant or one-probe-per-zone assumptions
- define drift checks

Success criterion:

> A few probes can calibrate many similar zones well enough for practical watering decisions.

## Phase 3 — Non-Pi photo recovery — DEFERRED (2026-06-08)

**Status: bulk run deferred.** The priors-first method was validated (blind A/B: kind-level 16/17,
overconfident-wrong 3→0, fixed the lemongrass↔garlic-chives swap) — _direction_ proven, banked. But
the balcony is research input, not the target; tagging all ~650 balcony herbs produces a
balcony-specific corpus of limited garden transfer. **Defer the bulk run, save the $4**; later tag a
curated **50–100** reference subset (recurring kinds, seedlings, canopy-stage, confusables),
tag-as-you-go. The point was never a catalogue — it's irrigation: photo → canopy/cover + P(kind) →
expected Kc, localized to a zone (variety is irrelevant to water demand). See vision-tagging.md
"Decision: DEFER" and irrigation.md "Garden scale". The original plan below stays as reference.

Goal: fix the photo-to-unit tagging blocker.

Tasks:

- make phone/camera import easy
- select 30–50 validation photos from the archive
- run A/B tagging validation:
  - thin prior
  - rich compact prior
- test suspected smoking guns:
  - resolution starvation
  - grid/photo-ID misassociation
  - open-world ID
  - missing date/state priors
  - missing container/composition priors
  - confusables forced into singles
  - seedlings over-labelled
  - self-confidence trusted
- build confirmed photo → growing-unit links
- label high-quality confirmed references
- only then consider full archive-scale tagging

Success criterion:

> Non-Pi photos can be tagged to growing units/zones with useful precision and tolerable review
> effort.

## Phase 4 — Manual requested photos

Goal: make future garden/greenhouse context scalable without fixed camera coverage everywhere.

Tasks:

- define capture request types:
  - bed
  - zone
  - tray
  - plant group
  - specific growing unit
- allow system to ask for a photo when context is stale or uncertain
- tag requested photos to unit/zone/state
- extract:
  - crop or crop mix
  - canopy bucket
  - crop stage
  - condition
  - moved / harvested / died-back / replanted
- feed useful context back to irrigation and cooking availability

Success criterion:

> A human can provide occasional photos, and the system turns them into useful plant/zone context
> without routine manual logs.

## Phase 5 — Bounded automation

Goal: move from recommendation to safe limited automatic watering.

Tasks:

- start with recommendations
- add bounded auto-dosing only after dose-response is understood
- fail closed on unknown pump/sensor/zone state
- treat overwatering as a real failure
- use conservative rain/forecast handling
- require confidence for aggressive corrections
- allow manual override
- log every automatic decision and dose

Success criterion:

> The system can safely water within bounded limits and explain why it dosed or refused to dose.

## Track D — Platform / import / review UX

This track supports all phases.

Important work:

- reliable phone/camera import
- stable photo IDs
- duplicate-ingest protection
- batch/run IDs for AI suggestions
- review UI for accept/edit/reject
- keyboard/mobile review
- confirmed reference labelling
- growing-unit / zone / bed identity hygiene
- export of context to irrigation:
  - sun exposure
  - canopy bucket
  - crop stage
  - state changes
- data integrity checks before large AI runs

This is boring infrastructure, but it is the difference between a clever demo and a usable system.

## Deferred / not now

- polished commercial UI
- generic plant-diagnosis product
- heavy Pi-side CV
- open-world plant identification
- dense sensor mesh
- one probe per plant
- gram-perfect harvest logging
- full archive tagging before small validation succeeds
- fully autonomous watering before bounded known-input tests
- ML experiments that do not feed tagging, context, or irrigation decisions

## Do not re-open these decisions

- Do not make basic irrigation depend on continuous camera reads.
- Do not design a one-probe-per-plant architecture.
- Do not treat Flower Care moisture percentage as absolute truth.
- Do not transfer balcony-pot coefficients directly to ground beds.
- Do not keep polishing inferred human-watering detection instead of adding known dosing.
- Do not rebuild the 256px contact-sheet tagging pipeline.
- Do not trust model self-confidence as an acceptance gate.
- Do not ask open-world plant ID when this is a closed-set matching problem.
- Do not force confusables into confident single labels.
- Do not require manual logs as normal operation.
- Do not bury durable failure lessons inside chronological narration.

## Near-term focus

The next useful work should concentrate on two parallel tracks:

1. **Irrigation hardware path**
   - choose pump/valve approach
   - record known doses
   - measure EC/moisture response
   - add safety gates

2. **Software/model/tagging path**
   - keep improving passive drydown model
   - add `Ks(moisture)` and coarse canopy terms carefully
   - make phone/camera import easier
   - run small non-Pi tagging validation
   - build confirmed reference corpus

The important discipline: do not wait for perfect AI before doing irrigation, and do not wait for
pump hardware before improving the model and tagging pipeline.

## Goal

A system that scales like this:

```text
few probes + microclimate sensors + forecast/rain + sun-map + canopy/context + known dosing
→ practical irrigation decisions
→ occasional photo/context correction
→ bounded automation
```

The strategic win is not a garden gadget. It is making serious, high-quality, climate-constrained
edible growing operationally possible beyond balcony scale.
