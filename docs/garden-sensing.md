# Garden Sensing — design sketch (pre-site)

_Status: design sketch, written 2026-06-09, **before** the garden site lands (~Sept/Oct 2026).
Nothing here is built yet. The point is to design the coordinate system, localization, capture
workflow, and per-photo outputs now, so September is execution and not improvisation._

This doc owns the **garden-scale sensing design**: how a mostly-handheld, marker-anchored photo
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
| identity | by overhead position | by physical marker + map |

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

## Localization = physical markers + a garden map (NOT pixel-recognition)

Cheap physical anchors beat clever vision. Bed labels / row stakes carry **AprilTag or ArUco**
fiducials; a small map table resolves `tag_id → site/bed/zone`.

A handheld photo localizes **priors-first**, the same shape as the tagging method:

```text
detected marker  →  bed/zone        (the anchor)
+ garden map     →  neighbours / layout
+ expected crop mix for that zone + timestamp + nearest prior state
→ localization with a confidence, NOT a pixel guess
```

- **Marker scheme:** at minimum one anchor per **bed** (coarse bed-level ID is enough — see below);
  encode the id in the tag; keep the `tag_id → location` map as first-class data (small,
  human-editable).
- **No marker in frame:** degrade gracefully — coarse position (user confirms "I'm at bed 3"), the
  prior, and crop mix; or mark _location-unknown, ask_. Never silently guess a zone from pixels.

Markers + map are **primary**; crop mix / plant identity is **secondary** evidence — used for
markerless shots, sanity checks, and ambiguity resolution, not as the main locator. This downgrades
(not deletes) the balcony "plants as fingerprint of location" idea.

### Localization is the design's main risk — de-risk it (resolved 2026-06-09)

Two answers tightened this: outdoor marker durability is **doubtful**, and markerless self-
localization of a closeup is **probably hard**. So don't depend on pristine fiducials or on a leaf
photo locating itself. Instead:

- **Aim for coarse BED-level localization, not precise within-bed pose.** The layout is static, so
  knowing _which bed you're standing at_ + the map is most of the job. A durable bed marker — laser-
  engraved/anodised metal or stamped tag, not printed plastic — plus user confirmation is robust and
  cheap. Precise fiducial geometry (and any px↔cm scale) is a **bonus, not a requirement**.
- **Closeups inherit location from a paired marked overview**, taken in the same visit, rather than
  self-localizing. The overview carries the marker; the closeup borrows its zone.
- **Identity helps locate** (not demand — see outputs): the crop mix narrows _which_ zone within a
  bed when the marker is coarse or absent.

## Capture metadata (per photo) — matters more than the model

The metadata is what makes a handheld shot into sensing. Per photo, capture:

- **timestamp** (existing `captured_at`).
- **site / bed / zone guess** + its **source** (marker / manual / gps) and confidence.
- **photo type:** overview / closeup / row / tray / problem / after-watering (extends `photo_type`).
- **source:** requested vs spontaneous, + a link to the **capture request** that prompted it.
- **scale:** px↔cm from a marker, when present.
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

## Minimum viable garden sensing loop

The smallest end-to-end loop that makes the design executable:

1. Put visible markers on beds/zones.
2. Take an initial marked overview photo for each bed.
3. Register expected crop patches/rows against the map.
4. When planting/transplanting changes, take a marked update photo.
5. On each visit, take requested overview photos for stale/uncertain zones.
6. The system outputs localization, canopy/surface state, and an optional kind distribution.
7. Irrigation uses those outputs as context, not as direct commands.

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

- Pick the marker family (AprilTag vs ArUco), tag size, and weatherproof print/mount.
- Define the `tag_id → location` map table + id encoding.
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
- **Marker durability / markerless closeups:** both shaky → coarse bed-level durable markers + map +
  user confirm; closeups inherit location from a paired overview (see Localization risk).

Still open:

- **Durable-localization detail:** which durable bed marker (engraved metal? stamped? size?) and is
  bed-level granularity actually enough in practice — _the design's biggest remaining risk._
- Where exactly the ~40 categories fall across the 3–5 demand classes (needs the crop plan).
- Capture cadence for an off-grid / visited-every-few-days site.

## Do not re-open (settled decisions)

- Localization is **markers + map**, not pixel-recognition.
- The irrigation unit is the **zone**, not the plant.
- Vision outputs **canopy + a kind distribution**, never a forced single label.
- **Variety is irrelevant** to water demand unless its `Kc` differs materially.
- **No _dependency_ on fixed dense camera** coverage; marker-anchored requested handheld photos are
  the scale path. Fixed cameras may still be used _opportunistically_ where cheap and stable (a
  greenhouse, a seedling bench, a high-value bed) — non-essential, not forbidden.
- Balcony move-detection / sun-chase / fixed-Pi region-map / pixel-as-primary-locator machinery does
  **not** transfer.
