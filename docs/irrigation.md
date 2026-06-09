# Irrigation / Water-Balance — primary product working doc

_Focused working doc for the irrigation track._

- For nursery direction, crop priorities, and scaling context, see [`nursery.md`](nursery.md).
- For camera monitoring, manual-photo tagging, identity/event detection, and AI tagging, see
  [`vision-tagging.md`](vision-tagging.md).

This doc owns: irrigation strategy, sparse sensing, water-balance modelling, probe calibration,
pump/dosing control, and irrigation-specific camera context.

This doc does **not** own: nursery strategy, general AI tagging, camera pipeline internals, database
schema, prompts, or historical narration.

## Product thesis

Watering is the one cost that scales almost linearly with plant count and does **not** compress much
with skill.

Sowing is seasonal. Selection improves with experience. Cooking can batch. But watering is daily,
non-deferrable, per-plant/per-zone, and grows with area.

Twice-daily hand-watering is fine on the balcony. At ~100 m² it becomes hours of labour. Across
multiple sites it becomes structurally impossible.

So the primary product is not "plant watching". It is a **closed-loop irrigation controller** that
lets the nursery scale on infrastructure instead of hands.

## Architecture for scale

The system must avoid per-plant infrastructure. The economics only work if sensing and vision are
sparse.

### Probes calibrate; they do not continuously sense every zone

A probe establishes soil/zone behaviour:

- drydown rate under different weather demand
- response after a known dose
- drift / sensor sanity checks
- rough `k` coefficients for similar zones

Then many similar zones can run from:

- weather and forecast
- local microclimate
- static sun/shade map
- coarse canopy/crop-stage context
- known pump dosing
- occasional probe checks

The target is **a handful of probes for calibration and drift anchors**, not one probe per plant or
every zone.

### Cameras calibrate context; they do not drive basic watering

Camera input is useful, but irrigation should not depend on continuous vision.

At architecture level, camera/tagging is an occasional context source: sun exposure, canopy/crop
stage, and major state changes. The concrete irrigation roles are detailed below in
[Camera / tagging role for irrigation](#camera--tagging-role-for-irrigation).

The scalable stack is:

```text
few probes + few microclimate sensors + forecast/rain input + static sun-map + coarse canopy/state + known dosing + balance model
```

## Current live model vs target model

### Live now

Current working pieces:

- forecast/archive integration
- live ET₀ calculation
- VPD from local temperature/RH sensors
- per-region sun-hours from camera **(preliminary)** — `sun_hours.py`. The 2026-06-09 multi-day
  re-run is done: the two full daytime arcs (06-07, 06-08) give a profile that is stable for most
  regions (±0–1.1 h/day; chillis + basils ~9–10 h top the ranking, mints/dill ~4.5 h bottom). A
  handful flip between the two days (Sage 9.0→3.2, Rosemary 9.0→4.0, Lemongrass 9.0→3.2) — a tool
  caveat (shade-baseline percentile shifts when 06-08's early-morning shaded frames are included),
  so still needs more clear days for the full standing profile. Drop evening-only partial arcs
  (06-06 was 17:00→00:00) before averaging. `water_balance_live.py` flags partial-day arcs.
  **Caveat (2026-06-09):** most frames (13/14, 14/17) FAIL single-reference registration under
  dawn→dusk lighting and fall back to raw identity geometry — `sun_hours.py` now reports this loudly
  instead of using it silently. Tolerable because the Pi mount is fixed (raw ≈ aligned), but the
  profile currently rests on that assumption; chained-hop or stored stabilization transforms are the
  real fix before the sun map is trusted as an irrigation input.
- `demand_mm = ET₀ × Kc × sun-fraction`
- watering-event inference from EC + soil-moisture response
- soil drydown analysis on the Cilantro Flower Care probe (VPD→drydown holds _qualitatively_; the
  fitted coefficient is method-sensitive — see Evidence)

### Target model

```text
per-zone soil-water balance over time:

moisture(t+1) = moisture(t) + irrigation + rain − ET_actual · dt

ET_actual = k · VPD · canopy · Ks(moisture)
```

Where:

- **VPD** is the local instantaneous evaporative-demand driver from temperature + humidity.
- **k** is the calibrated per-zone/soil depletion coefficient.
- **canopy** is a coarse **canopy-cover / transpiring-surface** multiplier — equivalent to FAO-56
  `Kc`. NOT true leaf-mass/biomass (hard from casual RGB); cover is what irrigation needs and is
  achievable. See "the demand model is solved agronomy" below.
- **Ks(moisture)** is the water-stress/supply-limitation factor: drydown slows as soil dries.
- **ET₀** is the portable reference-demand forecast used for forward planning.

The model does not need perfect biological accuracy. It needs good enough per-zone dosing decisions
with conservative safety limits.

### The demand model is solved agronomy — adopt, don't invent (2026-06-08)

Cross-checked: the canopy→demand path is established irrigation science, not something to invent.
FAO-56's `ETc = Kc × ET₀` already folds crop type, **growth stage, and ground cover** into `Kc`. Use:

```text
zone_demand ≈ ET₀ × Kc(stage/cover) × Ks(moisture)            # single coefficient
zone_demand ≈ ET₀ × (Kcb_canopy + Ke_bare_soil)               # FAO-56 DUAL coefficient
```

The **dual coefficient** is the better form for the garden: it splits canopy transpiration (`Kcb`)
from bare-soil evaporation (`Ke`), which matters for **newly-sown / sparse beds** where soil
evaporation dominates. `Kc` from **fraction-of-ground-cover + crop height** is a documented method,
and **canopy-cover / LAI from RGB images** is established — so the camera term is a known build, not
research. Implication: estimate **cover + stage**, not plant identity or biomass.

**Wired (2026-06-09).** The dual form is now in code:

- `water_demand.basal_kc_from_cover(fc, …)` — `Kcb` from ground-cover fraction `fc` via the Allen &
  Pereira (2009) density coefficient (`fc=1 → Kcb_full`, `fc=0 → Kcb_min`).
- `water_demand.soil_evap_kc(kcb, fc, kr, …)` — `Ke` (FAO-56 eq.71); big for a bare freshly-wetted
  bed, →0 under full canopy (`fc→1`) or a dry surface (`kr→0`).
- `water_demand.dual_demand_mm(et0, kcb, ke, sun)` = `ET₀ × (Kcb + Ke) × sun` (converges to the
  single-`Kc` demand for dense zones).
- `water_balance.COVER_FC` maps the canopy buckets (bare/newly-sown/seedlings/sparse/moderate/heavy)
  → representative `fc`, and `water_balance.dual_coeffs(name, bucket, kr)` returns `(Kcb, Ke)` — the
  hook a vision/manual-photo canopy read feeds. Covered by `test_water_demand.py` /
  `test_water_balance.py`. The live join still needs a per-unit canopy/`kr` source before it drives
  real dosing.

## Validated state as of 2026-06-08

### Operational pieces

- **Demand side built and live**
  - `scripts/water_demand.py`
  - `forecast_et0.py`
  - FAO-56 ET₀, 10/10 validated
  - live forecast feed
  - VPD per microclimate sensor
  - per-region sun-hours from camera via `sun_hours.py`
  - joined in `water_balance.py`

- **Supply side started**
  - `watering_detector.py`
  - watering-event detection from EC + moisture fusion
  - auto-pump/valves are the planned unlock
  - **Open question (pre-site, UNCONFIRMED):** _if_ the plot turns out to have pressurised water,
    the "unlock" might be **solenoid valves on a pressurised line rather than a pump** — simpler, no
    pump to source. This is a hypothesis to check when the site lands, not a known fact; **the pump
    stays the working assumption until confirmed.** Either way the control logic (known dose →
    measure response) is unchanged; only the actuator differs.

### Evidence — VPD→drydown is qualitative, NOT a stable fitted coefficient (revised 2026-06-09)

On the one instrumented pot (Cilantro Flower Care, ~16 days), a measured soil-moisture drydown does
rise with evaporative demand: VPD is the best short-term predictor (hourly, zone-local), ahead of air
temperature and daily ET₀. That **qualitative** relationship is robust, and is clearest at the
**per-interval** level once quantisation artefacts are guarded (`Spearman(rate, VPD) ≈ +0.6`).

But the **fitted depletion coefficient is not robust.** An earlier headline (`drydown ≈ 13.5·VPD −
10.5`, `R² = 0.39`, Spearman +0.71) does **not** reproduce: re-running `soil_drydown.py` across
defensible method changes — full-resolution fetch (5000 vs 400 points), and splitting drydowns on
**re-wetting events** instead of a moisture-jump threshold — swung the segment-level fit anywhere from
`R² ≈ 0.39` down to `R² ≈ 0.01–0.07`. The segment-level `k` depends strongly on **watering-event
segmentation** and **probe resolution**, both of which are themselves unsolved (watering detection is
provisional; Flower Care moisture is integer-quantised). Treat `k` as **not yet a fitted constant.**

Residual / confounding sources: watering-event segmentation, moisture quantisation, unmodelled canopy
/ crop stage, and pot-specific behaviour that will not transfer to ground beds anyway. **The method
transfers; the balcony pot coefficient does not.**

### Crack #2 — `Ks(moisture)`: unresolved / method-sensitive (2026-06-09)

`soil_drydown.py` carries a `Ks(moisture)` probe (`ks_intervals`): within each drydown it computes
per-interval rates (guarded to ≥2 h apart so a single integer moisture step can't dominate) and
**divides VPD out** (`y = rate / VPD = k · Ks(moisture)`), so a remaining trend of `y` vs moisture
**level** is the supply-limitation (FAO-56 `Ks`) signature — drier soil should drydown slower.

**The result is method-sensitive and currently inconclusive.** The sign of
`Spearman(rate/VPD, moisture)` **flips** with segmentation and quantisation handling (observed −0.27
with one method, +0.38 with another in the same session). So `Ks` is **neither absent nor
confirmed** — do not add a `Ks` term to the production model, and do not record it as ruled out.

The blocker is not more passive probe-days. Fitting a reliable `k` or `Ks` needs **known pump dosing
and/or ground-truth watering labels** so drydown segments are correctly bounded — the same
known-input unlock the rest of this doc points to. Re-running `soil_drydown.py` will keep producing
method-dependent numbers until then.

## Sparse-probe calibration protocol

Use probes to learn zone behaviour, not to create dense sensor infrastructure.

A practical calibration loop:

1. Put a probe in a representative pot, bed, soil type, or irrigation zone.
2. Observe drydown across several weather cycles.
3. Fit depletion against VPD / ET₀ / sun exposure / canopy state.
4. Apply a known dose.
5. Measure EC + moisture response after dosing.
6. Estimate infiltration, retention, and response lag.
7. Reuse the learned coefficient for similar zones.
8. Keep one or a few probes as drift anchors.
9. Recalibrate when soil, container/bed type, crop density, season, or irrigation hardware changes
   materially.

Important: **ground beds need their own calibration**. Balcony pot `k` is not portable to ground
because soil depth, drainage, rooting volume, and retention are different.

## Camera / tagging role for irrigation

Irrigation does not need camera input to know that a pump ran or that a probe responded.

It may still benefit from visual context in two ways.

### 1. Static or slow-changing sun map

Sun exposure / insolation is a major per-zone demand difference.

This can often be treated as a calibration task:

- map which zones get full sun, partial sun, or shade
- estimate sun-hours / exposure by zone
- refresh when layout changes or season materially changes
- do not require continuous camera coverage

A fixed Pi camera can help on the balcony or a small greenhouse. It probably will not scale cleanly
to larger plots or multiple sites.

### 2. Occasional canopy / crop-stage context

A bare seeded bed, seedlings, moderate canopy, and heavy leaf canopy do not have the same water
demand under the same weather.

The model only needs coarse buckets:

- bare / newly sown
- seedlings
- sparse canopy
- moderate canopy
- heavy canopy

This can come from overhead images, closeups, manual photos, or manual correction.

For larger areas, the likely scalable approach is **requested manual photos**: ask for a photo of a
bed, zone, tray, or plant group when the model needs context. That only works if tagging can
identify:

- bed / zone / tray / plant group
- crop or crop mix
- canopy bucket
- crop stage
- major state changes: moved, harvested, died back, replanted

So tagging is a support layer for irrigation context, not the core irrigation sensor.

**Irrigation consequence of a move (this doc owns it):** when a zone/pot is flagged _moved_ (the
detection itself lives in vision-tagging.md), irrigation must **drop that zone's camera sun-fraction
until it is re-acquired** — otherwise the demand calc is contaminated by the _vacated spot's_ sun.
Concretely the chillis: after their sun-driven afternoon move to the West window, their old overhead
tag reads the empty sunny spot, not the plant, so their camera sun-fraction is currently
contaminated.

## Control and safety principles

Before auto-pump becomes trusted, the doc should preserve these constraints.

- Fail closed if pump state, sensor state, or zone mapping is unknown.
- Treat overwatering as a real failure, not merely a harmless conservative choice.
- Use max dose per zone per cycle.
- Use cooldown between repeated doses.
- Prefer several small corrections over one large blind correction.
- Rain forecast can reduce planned dosing but should not erase observed deficit blindly.
- Sensor outliers should degrade to conservative schedule/model behaviour.
- Camera/tagging uncertainty should reduce confidence, not block basic watering.
- Manual corrections should be occasional, not required for normal operation.
- Known dosing should replace inferred human watering as soon as practical.

The first auto-pump target is not "fully autonomous garden". It is controlled known-input
experiments:

`sense → dose → measure response → adjust`

## Data sources / implementation notes

### ESP32 home-display server

`SENSOR_API_URL=https://laptop.local:8000`

Uses `X-Api-Key`.

Endpoints:

- `GET /openmeteo/weather?start_ts&end_ts`
  - includes weather demand and rain inputs, including Open-Meteo rain / showers variables used as
    water-balance supply
- `GET /sensors`
- `GET /sensors/{id}/readings?start_ts&end_ts&max_points`
- `GET /sensors/latest`

The backend container can resolve `laptop.local`.

### Sensors

SwitchBot temperature/RH:

- **South**: railing, cool/exposed
- **South wall**: hot/dry
- **West**: chilli afternoon window
- **Bed**: indoor, exclude from balcony outdoor demand

Xiaomi **Flower Care** probe:

- Cilantro pot
- moisture / light / temperature / EC
- current ground-truth calibration anchor

### Scripts

- `water_demand.py`: VPD, ET₀, single Kc, and the FAO-56 dual coefficient
  (`basal_kc_from_cover` / `soil_evap_kc` / `dual_demand_mm`)
- `forecast_et0.py`: live daily ET₀
- `water_balance.py`: joined demand model + per-species Kc; canopy-bucket→`fc` map (`COVER_FC`) and
  `dual_coeffs` for the dual form
- `soil_drydown.py`: drydown/demand validation + depletion fit + the `Ks(moisture)` probe
  (`ks_intervals`)
- `watering_detector.py`: EC + moisture watering-event detection
- `sun_hours.py`: camera-derived sun-hours / exposure context

`soil_drydown.py` and `water_demand.py` are numpy-free.

## Garden scale — design before the site (~Sept/Oct 2026)

_Full design: [`garden-sensing.md`](garden-sensing.md). This section is the irrigation-side summary._

The balcony is research input; the real target is the ground garden, where the problem is **different
and simpler**: ground plants stay put (no sun-chasing / moving pots), there is no fixed overhead
camera, and the dynamic is mostly "**detect a new plant**" against an otherwise static layout. Design
these now so September isn't improvised:

- **Coordinate system:** `site → bed → zone → patch/row → unit/group`. The irrigation unit is the
  **zone/bed-section**, NOT "plant". Demand and valves are per-zone.
- **Localization = physical markers + a garden map, NOT pixel-recognition.** Cheap bed labels / row
  stakes / **AprilTag/ArUco anchors** beat clever vision. A handheld photo localizes via
  `marker + map + expected crop mix + timestamp + nearest prior state` — priors-first, again. (This
  retires the balcony "plants as the fingerprint of location" idea — markers are cheaper and surer.)
- **Requested-photo workflow:** the system asks for _useful_ photos ("overview of Bed 2 from the
  south end", "closeup of Zone 3 left half", "photo after watering"), not random ones — that's how
  handheld shots become sensing.
- **Capture metadata per photo:** timestamp, site, bed/zone guess, photo type (overview / closeup /
  row / tray / problem), source, scale if available, requested-vs-spontaneous + linked capture
  request. This metadata matters more than the model.
- **Three separate per-photo outputs — don't let identity swallow the task:**
  1. **localization** — which bed/zone/patch (from marker/map);
  2. **canopy/surface** — bare / seedling / sparse / moderate / heavy + approx green fraction (the
     demand signal — see the dual-Kc model above);
  3. **identity** — a probability distribution over kind/group (variety only if its Kc differs
     materially); store raw probabilities + whether the uncertainty actually changed demand, to learn
     later if they're calibrated or decorative.

## Do not re-open these traps

- Do not make basic irrigation depend on continuous camera observation.
- Do not design one probe per plant or one probe per zone as the scaling assumption.
- Do not transfer balcony-pot `k` directly to ground beds.
- Do not treat Flower Care moisture percentage as absolute truth.
- Do not keep polishing inferred human-watering detection instead of adding known pump dosing.
- Do not require manual logs.
- Do not treat garden-average watering as good enough for quality crops.
- Do not confuse vision/tagging support with the primary irrigation product.

## Build order

1. Preserve the current demand model.
2. Add known-input pump dosing.
3. Record dose events cleanly: zone, time, volume/duration, pump/valve state.
4. Measure EC + moisture response after known doses.
5. Fit response curves per probe/zone.
6. Add `Ks(moisture)` to account for drydown slowdown.
7. Add coarse canopy/crop-stage buckets.
8. Add static or slow-changing sun-map per zone.
9. Move from recommendations to bounded auto-dosing.
10. Recalibrate for ground beds when the system moves beyond balcony pots.

## Constraints inherited from nursery strategy

- One-person project.
- No reliable manual logs.
- Balcony now, garden later.
- Pots now, ground later.
- Future garden may be off-grid or visited only every few days.
- Power, water storage, pressure, and maintenance are real site constraints.
- Underwatering and overwatering are both quality/survival risks.
- Warm-tender crops are the edge, so control has to preserve quality, not only survival.

## Goal

Build a closed-loop irrigation controller that scales from balcony to garden.

The core loop is:

```text
sense → dose → observe → adjust
```

The strategic win is sparse calibrated irrigation: a system where a few probes, occasional visual
context, known dosing, and a weather-driven model can control many plants/zones without daily manual
watering labour.
