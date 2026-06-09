# Irrigation / Water-Balance — primary product working doc

_Focused working doc for the irrigation track._

- For nursery direction, crop priorities, and scaling context, see [`nursery.md`](nursery.md).
- For camera monitoring, manual-photo tagging, identity/event detection, and AI tagging, see [`ai-tagging-design.md`](ai-tagging-design.md).

This doc owns: irrigation strategy, sparse sensing, water-balance modelling, probe calibration, pump/dosing control, and irrigation-specific camera context.

This doc does **not** own: nursery strategy, general AI tagging, camera pipeline internals, database schema, prompts, or historical narration.

## Product thesis

Watering is the one cost that scales almost linearly with plant count and does **not** compress much with skill.

Sowing is seasonal. Selection improves with experience. Cooking can batch. But watering is daily, non-deferrable, per-plant/per-zone, and grows with area.

Twice-daily hand-watering is fine on the balcony. At ~100 m² it becomes hours of labour. Across multiple sites it becomes structurally impossible.

So the primary product is not "plant watching". It is a **closed-loop irrigation controller** that lets the nursery scale on infrastructure instead of hands.

## Architecture for scale

The system must avoid per-plant infrastructure. The economics only work if sensing and vision are sparse.

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

The target is **a handful of probes for calibration and drift anchors**, not one probe per plant or every zone.

### Cameras calibrate context; they do not drive basic watering

Camera input is useful, but irrigation should not depend on continuous vision.

At architecture level, camera/tagging is an occasional context source: sun exposure, canopy/crop stage, and major state changes. The concrete irrigation roles are detailed below in [Camera / tagging role for irrigation](#camera--tagging-role-for-irrigation).

The scalable stack is:

`few probes + few microclimate sensors + forecast/rain input + static sun-map + coarse canopy/state + known dosing + balance model`

## Current live model vs target model

### Live now

Current working pieces:

- forecast/archive integration
- live ET₀ calculation
- VPD from local temperature/RH sensors
- per-region sun-hours from camera **(preliminary)** — `sun_hours.py` is a prototype pending multi-day / full-arc validation (the 2026-06-09 check); `water_balance_live.py` flags its sun-fraction as partial-day
- `demand_mm = ET₀ × Kc × sun-fraction`
- watering-event inference from EC + soil-moisture response
- first soil drydown validation on the Cilantro Flower Care probe

### Target model

```text
per-zone soil-water balance over time:

moisture(t+1) = moisture(t) + irrigation + rain − ET_actual · dt

ET_actual = k · VPD · canopy · Ks(moisture)
```

Where:

- **VPD** is the local instantaneous evaporative-demand driver from temperature + humidity.
- **k** is the calibrated per-zone/soil depletion coefficient.
- **canopy** is a coarse crop/leaf-area multiplier, equivalent in spirit to FAO-56 `Kc`.
- **Ks(moisture)** is the water-stress/supply-limitation factor: drydown slows as soil dries.
- **ET₀** is the portable reference-demand forecast used for forward planning.

The model does not need perfect biological accuracy. It needs good enough per-zone dosing decisions with conservative safety limits.

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

### Evidence

On the one instrumented pot, Cilantro Flower Care, 14 days, 12 drydown segments between watering events:

- drydown rate vs air temperature: Spearman **+0.49**
- drydown rate vs VPD: Spearman **+0.71**
- drydown rate vs daily ET₀: Spearman **+0.52**

VPD is the best validated short-term predictor so far because it is hourly and zone-local.

Magnitude was large:

- cool spell around 20 °C: about **1.8 %/day**
- hot days: about **24–34 %/day**

First depletion fit:

```text
drydown ≈ 13.5 · VPD − 10.5 %/day
R² = 0.39
```

This is monotonic but noisy. Likely residual sources:

- unmodelled canopy / crop stage
- missing `Ks(moisture)`
- Flower Care moisture quantisation / nonlinearity
- pot-specific behaviour that will not transfer directly to ground beds

The method transfers. The balcony pot coefficient does not.

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
9. Recalibrate when soil, container/bed type, crop density, season, or irrigation hardware changes materially.

Important: **ground beds need their own calibration**. Balcony pot `k` is not portable to ground because soil depth, drainage, rooting volume, and retention are different.

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

A fixed Pi camera can help on the balcony or a small greenhouse. It probably will not scale cleanly to larger plots or multiple sites.

### 2. Occasional canopy / crop-stage context

A bare seeded bed, seedlings, moderate canopy, and heavy leaf canopy do not have the same water demand under the same weather.

The model only needs coarse buckets:

- bare / newly sown
- seedlings
- sparse canopy
- moderate canopy
- heavy canopy

This can come from overhead images, closeups, manual photos, or manual correction.

For larger areas, the likely scalable approach is **requested manual photos**: ask for a photo of a bed, zone, tray, or plant group when the model needs context. That only works if tagging can identify:

- bed / zone / tray / plant group
- crop or crop mix
- canopy bucket
- crop stage
- major state changes: moved, harvested, died back, replanted

So tagging is a support layer for irrigation context, not the core irrigation sensor.

**Irrigation consequence of a move (this doc owns it):** when a zone/pot is flagged *moved* (the detection itself lives in ai-tagging-design.md), irrigation must **drop that zone's camera sun-fraction until it is re-acquired** — otherwise the demand calc is contaminated by the *vacated spot's* sun. Concretely the chillis: after their sun-driven afternoon move to the West window, their old overhead tag reads the empty sunny spot, not the plant, so their camera sun-fraction is currently contaminated.

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

The first auto-pump target is not "fully autonomous garden". It is controlled known-input experiments:

`sense → dose → measure response → adjust`

## Data sources / implementation notes

### ESP32 home-display server

`SENSOR_API_URL=https://laptop.local:8000`

Uses `X-Api-Key`.

Endpoints:

- `GET /openmeteo/weather?start_ts&end_ts`
  - includes weather demand and rain inputs, including Open-Meteo rain / showers variables used as water-balance supply
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

- `water_demand.py`: VPD, ET₀, Kc
- `forecast_et0.py`: live daily ET₀
- `water_balance.py`: joined demand model + per-species Kc
- `soil_drydown.py`: drydown/demand validation + depletion fit
- `watering_detector.py`: EC + moisture watering-event detection
- `sun_hours.py`: camera-derived sun-hours / exposure context

`soil_drydown.py` and `water_demand.py` are numpy-free.

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

The strategic win is sparse calibrated irrigation: a system where a few probes, occasional visual context, known dosing, and a weather-driven model can control many plants/zones without daily manual watering labour.
