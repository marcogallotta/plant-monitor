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

- **Marker scheme:** at minimum one anchor per bed; optionally one per zone. Encode the id in the
  tag; keep the `tag_id → location` map as first-class data (small, human-editable).
- **Scale for free:** a known marker size gives px↔cm, so a marker in frame also yields a rough
  green-fraction scale (feeds canopy cover).
- **No marker in frame:** degrade gracefully — coarse GPS + user confirm + prior, or mark
  _location-unknown, ask_. Never silently guess a zone from pixels.

Markers + map are **primary**; crop mix / plant identity is **secondary** evidence — used for
markerless closeups, sanity checks, and ambiguity resolution, not as the main locator. This
downgrades (not deletes) the balcony "plants as fingerprint of location" idea: markers are cheaper
and surer and survive growth/harvest/lighting that defeat appearance-based matching, but the
expected crop mix still earns its place as a consistency check.

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
   - _canopy bucket:_ `bare → seedling → sparse → moderate → heavy` + an approximate green fraction.
   - _surface state:_ bare soil / mulch / wet-looking / crusted-dry / newly-sown-germinating / weed
     cover / residue / shade cloth — this drives the bare-soil evaporation term `Ke`, which the
     canopy bucket alone misses.
   Maps onto the dual-`Kc` hook already built: bucket → `COVER_FC` → `fc` → `(Kcb, Ke)` via
   `water_balance.dual_coeffs`, with surface state informing `Ke`. **Caveat:** a handheld oblique
   photo gives a _bucketed/approximate_ canopy signal, not a measured ground-cover percentage —
   perspective, occlusion, angle, and lighting all bite. Marker scale helps but does not solve them.
   Treat `fc` as approximate unless the photo follows a defined capture pose.
3. **Identity** — a **probability distribution over kind / group**, never a forced single label.
   Kind is _secondary to canopy_ for immediate demand, but not irrelevant: it sets the default
   `Kcb`/stage prior and the staleness cadence (fast leafy vs slow woody). Variety only when its `Kc`
   differs materially (mostly it doesn't). Store the raw probabilities _and_ whether that uncertainty
   actually changed the demand number — so we can later learn whether the identity read is calibrated
   or merely decorative.

## How it feeds irrigation

```text
photo →  zone            (marker + map)
      →  canopy bucket   → fc → (Kcb + Ke)      (water_balance.dual_coeffs)
      →  kind dist       (mostly irrelevant to water demand)

zone demand ≈ ET₀ × (Kcb + Ke) × sun_fraction(zone) × Ks(zone)
```

Sparse probes calibrate each zone's `k` (and recalibrate per ground-bed soil — balcony `k` does not
transfer); canopy reads from requested photos update `Kcb`; markers keep zone identity stable. This
design supplies exactly the **per-zone canopy / `kr` source the live dual-`Kc` model currently
lacks** (see irrigation.md "Wired" note).

## To decide / build before the site

- Pick the marker family (AprilTag vs ArUco), tag size, and weatherproof print/mount.
- Define the `tag_id → location` map table + id encoding.
- Extend the location model to `site / bed / zone / patch`.
- Minimal **capture-request** + **photo-metadata** schema (small, additive).
- A coarse **canopy-bucket estimator** from a single handheld photo (reuse priors-first; coarse is
  fine — irrigation only needs the bucket + rough green fraction).
- Zone granularity + valve mapping (couples to the pump/valve track — Phase 1).

## Open questions

- Zone size / how many zones for ~100 m²? (Sets probe count, valve count, request load.)
- Marker durability outdoors — UV, mud, frost, glare on the fiducial?
- One marker per bed enough, or per zone, for reliable localization at useful angles?
- Localizing a **closeup with no marker in frame** — scale + which zone, from prior + neighbours?
- Is coarse green-fraction from a handheld RGB photo robust to angle/lighting, or does it need the
  marker scale + a fixed-ish capture pose?
- How much does the kind-distribution actually move demand — i.e. is storing identity worth it
  beyond canopy, or is canopy + zone enough for watering?
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
