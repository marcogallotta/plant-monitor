# Garden Sensing — design sketch (pre-site)

_Status: design sketch, written 2026-06-09, **before** the garden site lands (~Sept/Oct 2026).
Nothing here is built yet. The point is to design the coordinate system, localization, capture
workflow, and per-photo outputs now, so September is execution and not improvisation._

This doc owns the **garden-scale sensing design**: how a mostly-handheld, location-tagged photo
stream becomes irrigation-relevant context for a ~100 m² ground garden.

- The irrigation model it feeds (zone demand, dual-`Kc`, sparse probes, `Ks`) lives in
  [`irrigation.md`](irrigation.md).
- The photo→unit tagging _method_ (priors-first, confusable policy, review loop) lives in
  [`vision-tagging.md`](vision-tagging.md). This doc reuses that method; it does not restate it.
- The strategy / scale trajectory lives in [`nursery.md`](nursery.md).

It does **not** own irrigation formulas, the tagging prompt/policy, or DB schema internals.

## Why the garden is a different — and simpler — problem

The balcony is research input, not the target. The garden inverts most of the hard balcony dynamics:

| | Balcony (now) | Garden (target) |
| --- | --- | --- |
| layout | movable pots, sun-chased | plants stay put |
| sensing | fixed overhead Pi, dense | no fixed overhead; sparse handheld photos |
| main dynamic | pots move / get rearranged | "a new plant / a changed zone" against a static map |
| identity | by overhead position | by capture-time binding + label + map |

So the garden problem reduces to: **localize a handheld photo to a zone, read its canopy, and note
change** — against an otherwise static layout. The irrigation unit is the **zone / bed-section, not
the plant**: demand and valves are per-zone.

**Balcony machinery that does NOT transfer** (do not port it): move detection, chilli sun-chase
modelling, the fixed-Pi region map, and "plants as the fingerprint of location."

## Coordinate system

```text
site → bed → zone → patch/row → unit/group
```

- **site** — a physical plot (the garden; later, possibly a second site).
- **bed** — a contiguous growing area (a raised bed, a row block).
- **zone** — _the demand-estimation unit:_ a bed-section expected to share water demand. Carries a
  demand calc and a probe-or-borrowed `k`.
- **patch / row** — sub-zone granularity for context (which end of the zone), not for valving.
- **unit / group** — a planting (a crop or crop mix) within a patch; the cooking/identity handle.

**Map zone vs hydraulic zone — don't force them equal yet.** A _map zone_ (above) is for
sensing/demand; a _hydraulic zone_ is what one valve actually waters. They may align 1:1 later, but
a first garden's plumbing is often awkward, so the data model must allow several map zones per valve,
or one map zone split across crop patches. Decide the mapping at the site, not now.

Maps onto existing data: today's `location_id` (balcony positions) generalises to the
site/bed/zone hierarchy; `growing_unit` stays the planting handle and gains a zone parent.

## Localization = capture-time binding + human-readable labels (NOT clever markers)

The robust way to know where a photo was taken is to **say so when taking it**, not to recover it
from pixels. Three layers, most-to-least reliable (resolved 2026-06-09):

1. **Capture-time binding (primary, the backbone).** Pick/type the target before shooting — e.g.
   `Bed 3 / sage mother-stock / 2026-05-12`. The requested-photo workflow already names the target
   ("Bed 3 overview"), so the response _is_ Bed 3; a one-tap "I'm at bed 3" covers spontaneous
   shots. **No computer vision needed.**
2. **Large human-readable labels (visual backup).** Big black-on-white codes a human _and_ OCR can
   read in a messy photo — `B3`, plus a smaller `Sage / mother-stock / planted 2026`. They degrade
   gracefully: a smudged or angled "B3" is still legible where a fiducial's binary pattern is not.
3. **Fiducials (optional bonus).** AprilTag/ArUco only on clean dedicated "reference" shots when
   precise pose/scale is wanted — never the core layer. They decode reliably only when clean, ~40+
   px, focused, near-frontal; mud / glare / occlusion / small-in-frame (the garden norm) break them,
   so durability and detectability are the _same_ problem. Don't depend on them.

Priors then finish the job, same shape as the tagging method — combining declared-or-read location,
the garden map, expected crop mix, timestamp, and nearest prior state into a zone with a confidence,
never a pixel guess. **Bed-level is the target granularity.** Closeups inherit their location from a
paired
overview in the same visit (markerless self-localization of a leaf shot is unreliable). Crop-mix
identity is a secondary consistency check that narrows _which_ zone — it helps locate, not water.

### Label conventions (boring on purpose — boring labels survive)

- **Location labels:** short bed/area codes in big text — `B1`, `B3` (beds), `PROP-2`
  (propagation), `M1` (mother-stock) — plus a smaller descriptive line. The code → `site/bed/zone`
  map stays first-class, small, and human-editable.
- **Plant / clone labels:** structured `CROP-VARIETY-NN` — `TAR-FR-01` (French tarragon clone 01),
  `SAGE-BG-02` (broadleaf sage line 02), `MINT-MOR-01` (Moroccan mint line 01). These ride on the
  `growing_unit` handle and double as the cooking/clone identity.

## Capture metadata (per photo) — matters more than the model

The metadata is what makes a handheld shot into sensing. Per photo, capture:

- **timestamp** (existing `captured_at`).
- **site / bed / zone** + its **source** (declared-at-capture / label-OCR / manual / fiducial) and
  confidence. Declared-at-capture is the common case.
- **photo type:** overview / closeup / row / tray / problem / after-watering (extends `photo_type`).
- **source:** requested vs spontaneous, + a link to the **capture request** that prompted it.
- **scale:** px↔cm from a fiducial, on the rare clean reference shot that carries one.
- **camera meta:** as already captured for Pi frames.

Extends the existing photo fields (`captured_at`, `location_id`, `photo_type`, `growing_unit_ids`)
rather than replacing them.

## Requested-photo workflow

The system asks for **useful** photos when context is stale or uncertain — not random ones. That is
how occasional handheld shots become a sensing stream without fixed cameras everywhere.

- **Request types:** zone overview ("Bed 2 from the south end"), targeted closeup ("Zone 3 left
  half"), after-watering verification, problem follow-up, tray/seedling check, and a
  **planting/update photo** (marker visible) taken whenever a zone changes.
- **Planting / change events** (the "detect a new plant" dynamic) ride on that update photo: newly
  sown bed, transplanted seedlings, replaced crop, harvested-out patch, fallow zone. A marked update
  photo is the **non-annoying replacement for manual logging** — capture the change once, with the
  marker in frame, instead of keeping a written log.
- **What triggers a request:** model uncertainty for a zone; staleness (weighted by crop growth
  speed — fast crops like rocket/basil go stale quickly, woody herbs slowly); a recent watering to
  verify; a flagged change.
- **Linkage:** every requested photo ties back to its capture request, so the response is
  interpreted against what was asked (which zone, what to look for).

This is the scalable replacement for fixed-camera coverage, and the bridge to Phase 4 of the
roadmap (manual requested photos).

## Capture: cadence, modes & tooling

### Cadence — confidence decay, not a fixed schedule (and not "never")

The control loop runs continuously on probes + VPD + forecast + dosing; photos only refresh slow
context. So capture is driven by **per-zone confidence decay**, not a calendar:

```text
zone state: canopy_bucket, surface_state, last_observed_at, confidence
confidence decays with: crop speed (fast leafy >> slow woody), elapsed time,
                        weather shocks (heat/rain), recent change events
→ request a photo when a zone's confidence drops, or an event is suspected
```

Indicative cadence (aligned to crop-scouting norms; piggybacks on visits you already make):

- newly sown / transplanted: higher, until established
- fast leafy / succession beds: ~weekly while active
- slow herbs / perennials / stable beds: ~every 2–4 weeks
- after extreme weather or an irrigation anomaly: an extra check

The system learns normal growth curves and lowers _routine_ cadence over time, but it must keep
_verifying_: it will never learn away failed germination, pests, heat/rain shock, weeds on bare
soil, a blocked emitter, or an unmarked harvest. So **"low cadence," never "none."**

### What photos are FOR (don't make irrigation pay cooking's cost)

| Use | Photo detail needed |
| --- | --- |
| irrigation | coarse zone overview (bucket) |
| crop map | marked overview / change photo |
| condition / problem | targeted closeup |
| cooking availability | closeup / manual check |

Irrigation needs coarse zone context; condition/cooking needs detail. Keep them separate so the
routine irrigation sweep stays cheap.

### Capture modes (build simplest first)

1. **Ad-hoc bound capture** (foundation): "photograph B3" → confirm/scan bed → 1–3 photos → metadata
   stored.
2. **Worklist** (the scaling path): "today: B3 overview, PROP-2, the bed you sowed Tuesday."
3. **Change/event capture** (critical): "I sowed / transplanted / harvested-out B3" → photo + event
   type. Without this the map silently rots.
4. **Per-bed mini-video** (later): tap B3, record 5–10 s, backend picks the best frames — redundancy
   without full-walk segmentation complexity.
5. **Full walkthrough video** (last, if ever): seductive but adds motion blur, frame selection,
   segmentation, storage/upload, and provenance problems. Defer until the data model is proven.

A walkthrough / oblique video yields **buckets only** — green-cover % is camera- and angle-dependent,
so a casual sweep cannot produce a calibrated cover number.

### Tooling — configure, don't build (yet)

- **Capture app:** don't write an Android app first. [Epicollect5](https://five.epicollect.net/)
  (Oxford; free, offline, custom forms, photo/video + **barcode**, CSV/JSON export) or ODK /
  KoboCollect already do bound capture + worklist-style forms. Prove the data model + review loop
  with a configured form; build custom only if friction demands it.
- **QR on labels:** a QR/barcode on each bed label gives reliable **scan-to-bind** location (scanned
  up close, unlike detecting a marker in a wide canopy shot) — alongside the big human-readable text.
- **Canopy read:** [Canopeo](https://apps.apple.com/us/app/canopeo/id929640529) (Oklahoma State;
  free) is a validated fractional-green-cover reference. Use it as the method reference and an
  _upgrade path_: a deliberate **downward (~1.5 m nadir)** shot per zone when a calibrated cover
  number is wanted. Routine oblique photos stay bucket-level — camera/angle dependence is exactly
  why we don't trust a handheld %.

### Build order

1. Define `site → bed → zone → patch`.
2. Make big human-readable labels (+ optional QR).
3. Ad-hoc bound capture (mandatory bed/zone binding) — via a configured Epicollect5 / ODK form.
4. Worklist capture.
5. Planting / change event capture.
6. Canopy / surface bucket review (backend).
7. Confidence decay + staleness-driven requests.
8. Per-bed mini-video frame extraction (later).
9. Full walkthrough video (only if needed).

## Three per-photo outputs — keep them separate

Do not let identity swallow the task. One photo yields **three independent outputs**, each stored
on its own, each with its own confidence:

1. **Localization** — which bed/zone/patch, from marker + map (above).
2. **Canopy / surface state** — the demand signal. Two parts:
   - _canopy bucket:_ `bare → seedling → sparse → moderate → heavy`. **Bucket only — do NOT emit a
     green-fraction percentage.** Handheld RGB isn't robust enough (perspective, occlusion, angle,
     lighting), confirmed 2026-06-09; a fake `fc` percentage is exactly the kind of false precision
     to avoid. The bucket maps to a _representative_ `fc` via `COVER_FC`, not a measured one.
   - _surface state:_ bare soil / mulch / wet-looking / crusted-dry / newly-sown-germinating / weed
     cover / residue / shade cloth — drives the bare-soil evaporation term `Ke`, which the canopy
     bucket alone misses.
   Maps onto the dual-`Kc` hook already built: bucket → `COVER_FC` → `fc` → `(Kcb, Ke)` via
   `water_balance.dual_coeffs`, with surface state informing `Ke`.
3. **Identity** — a **probability distribution over kind / group**, never a forced single label.
   Its primary value is **localization, not demand** (confirmed 2026-06-09): for watering, canopy
   alone drives the number; identity's job is to help pin _which zone_ a marker-coarse or markerless
   photo belongs to (the crop-mix consistency check above). It also sets the default staleness
   cadence (fast leafy vs slow woody). Variety only matters when its `Kc` differs materially (rare).

## How it feeds irrigation

```text
photo →  zone            (marker + map; kind dist helps locate)
      →  canopy bucket   → fc → (Kcb + Ke)      (water_balance.dual_coeffs)

zone demand ≈ ET₀ × (Kcb + Ke) × sun_fraction(zone) × Ks(class)
```

Canopy reads from requested photos update `Kcb`; markers + map keep zone identity stable. This
design supplies exactly the **per-zone canopy source the live dual-`Kc` model currently lacks** (see
irrigation.md "Wired" note).

### Probe budget forces classes, not per-zone calibration (2026-06-09)

Hard constraint: the budget is **1–2 more** waterproof probes (~€30 each), so **≤3 total** for the
whole garden — far fewer than zones. So probes cannot calibrate per zone. Instead:

- Collapse the ~**40 plant categories** into a **handful of demand classes** (e.g. thirsty-leafy /
  moderate-herb / woody-low-demand / seedling-or-bare), keyed on water demand + soil + exposure, NOT
  on species. The dual-`Kc` model already makes variety irrelevant, so this is cheap.
- The 2–3 probes calibrate the **representative class × soil**, and act as rotating drift anchors —
  moved to whatever class/zone is least trusted, not pinned one-per-zone.
- Every other zone runs on weather + VPD + canopy bucket + known dosing, **borrowing** its class's
  `k`. This is the sparse-calibration thesis pushed to its limit by the probe ceiling.

So "how many zones" is a layout/plumbing question (many), decoupled from "how many calibration
classes" (≈3–5, matched to the probes).

## To decide / build before the site

- Design the **human-readable label scheme** (bed codes + plant/clone codes above) and a durable,
  weatherproof way to print/mount them; fiducials optional for reference shots only.
- Define the `code → location` map table + capture-time location-binding UX.
- Extend the location model to `site / bed / zone / patch`.
- Minimal **capture-request** + **photo-metadata** schema (small, additive).
- A coarse **canopy-BUCKET classifier** from a single handheld photo (reuse priors-first; bucket
  only, no green-fraction percentage).
- Define the **~3–5 demand classes** (× soil) the 2–3 probes will calibrate.
- Zone granularity + valve mapping (couples to the pump/valve track — Phase 1).

## Resolved (2026-06-09) and what remains

Answered:

- **Probe budget:** ≤3 total → calibrate demand _classes_, not zones (see above).
- **Green-fraction:** not robust from handheld → **bucket only**, no percentage.
- **Identity vs demand:** canopy drives demand; identity's role is **localization** help.
- **Marker durability / markerless closeups:** both shaky → **don't lean on machine-vision markers.**
  Localization is now **capture-time binding** (primary) + large human-readable labels (backup) +
  fiducials optional. This _downgrades_ what was the biggest risk: localization no longer depends on
  reading a clean fiducial from a messy photo.
- **Cadence:** not daily, not "never" — **confidence-decay driven** (~weekly for active leafy,
  ~2–4 weeks stable, higher at establishment); piggybacks on visits. The learning loop lowers
  _routine_ checks but never removes _verification_.
- **Build vs configure:** prototype capture with **Epicollect5 / ODK**, don't write an app first.
- **Video:** later mode (per-bed mini-video first; full walkthrough last), buckets only.

Still open:

- **Label production:** a durable, weatherproof way to print/mount big human-readable codes (+ QR) —
  a procurement/making detail now, not an architecture risk.
- Where exactly the ~40 categories fall across the 3–5 demand classes (needs the crop plan).
- Capture cadence for an off-grid / visited-every-few-days site (lower bound on staleness).

## Do not re-open (settled decisions)

- Localization is **capture-time binding + human-readable labels + map**, not pixel-recognition and
  not machine-vision fiducials as the core layer.
- The irrigation unit is the **zone**, not the plant.
- Vision outputs **canopy + a kind distribution**, never a forced single label.
- **Variety is irrelevant** to water demand unless its `Kc` differs materially.
- **No _dependency_ on fixed dense camera** coverage; marker-anchored requested handheld photos are
  the scale path. Fixed cameras may still be used _opportunistically_ where cheap and stable (a
  greenhouse, a seedling bench, a high-value bed) — non-essential, not forbidden.
- Balcony move-detection / sun-chase / fixed-Pi region-map / pixel-as-primary-locator machinery does
  **not** transfer.
