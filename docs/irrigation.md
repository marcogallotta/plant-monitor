# Irrigation / Water-Balance — the primary product

_Focused working doc for the irrigation track. The vision/tagging/event-detection work (a
**supporting** layer) lives in [ai-tagging-design.md](ai-tagging-design.md); the project/nursery
context in [nursery.md](nursery.md)._

## Why this is the primary product

Watering is **the one cost that scales linearly with plant count and does not compress with
skill** — daily, non-deferrable, per-plant, growing in lockstep with area. Twice-daily
hand-watering is fine on the balcony, hours/day at 100 m², impossible across two sites.
Automating it **decouples plant-count from daily labour** → the difference between scaling on
*hands* vs *infrastructure*, and what makes the planned ~100 m² (2026) → 300–500 m² solo garden
feasible. Crucially it **does not depend on the vision/condition reads that keep failing** — it
runs on cheap sensors + free forecast + slow-changing geometry, all on the *forgiving* side of
accuracy (water a zone 20 % off and the plant is fine).

## The model

```
per-zone soil-water balance over time:
  moisture(t+1) = moisture(t) + irrigation + rain − ET_actual·dt
  ET_actual     = k · VPD · canopy · Ks(moisture)
```

- **VPD** (vapour-pressure deficit, kPa) — the instantaneous evaporative-demand driver, from
  temp + humidity. Pot/zone-local temp + ambient RH. The validated predictor (below).
- **k** — a per-zone/soil **depletion coefficient** (%moisture/day per kPa VPD). *Calibrated once
  per soil-type/zone with a probe*, then reused — the key to sparse sensing.
- **canopy** — leaf-area multiplier (= FAO-56 `Kc`). The missing term in the first fit. **Can be
  COARSE** (3 buckets: sparse/medium/full) from overhead green-coverage *or* a manual toggle — it
  does NOT need harvest-grade accuracy.
- **Ks(moisture)** — water-stress factor: drydown slows as soil dries (supply- vs demand-limited).
  Not yet modelled (next crack).
- **ET₀** (FAO-56 Penman-Monteith, mm/day) — the reference demand from forecast; the *forward*
  term for dosing ahead of a hot clear day. Weaker than VPD at sub-day resolution (daily, not
  zone-local) but the portable, location-independent quantity.

## Validated state (2026-06-08)

- **Demand side built & live** — ET₀ (`scripts/water_demand.py` + `forecast_et0.py`, FAO-56,
  10/10 validated, live off the forecast), VPD (per micro-climate sensor, live), per-region
  sun-hours from the camera (`sun_hours.py`), joined as `demand_mm = ET₀ × Kc × sun-fraction`
  (`water_balance.py`).
- **Crack #1 / #1b — demand drives soil drydown (`scripts/soil_drydown.py`).** On the one
  instrumented pot (Cilantro Flower Care, 14 days, 12 drydown segments between waterings):
  drydown rate vs proxy (Spearman) — air temp **+0.49**, **VPD +0.71** (winner: hourly,
  zone-local), daily ET₀ **+0.52**. Magnitude: cool spell (20 °C) **1.8 %/day** vs hot days
  **24–34 %/day** (~15×). First depletion fit: `drydown ≈ 13.5·VPD − 10.5 %/day` (R²=0.39;
  monotonic but noisy — residual is mostly the unmodelled **canopy** + Ks + FlowerCare nonlinearity).
- **Supply side** — watering-event detection from the probe (EC+moisture fusion,
  `watering_detector.py`, built). **Auto-pump = the planned unlock**: turns watering from an
  inferred event into a *known input*, which lets the control loop close.

## Architecture for scale (sparse by design)

- **Probes CALIBRATE, they don't continuously sense.** A probe establishes `k` for a
  soil-type/zone once; the zone then runs open-loop on VPD + `k` + a static sun-map. → a *handful*
  of probes to cover the garden's soil variety (+ maybe one drift-anchor), **not one per zone**.
- **Cameras may NOT scale broadly** — and don't need to. A fixed bed's sun exposure is
  geometry-driven and slow → a **measure-once-reuse static per-zone sun-map** (solar geometry + a
  one-time shade survey, refreshed seasonally; camera as a *calibration instrument*, not
  per-zone infrastructure).
- **Coarse canopy level** per zone (overhead green-coverage *or* manual), low accuracy bar.
- **Scalable stack:** few calibration probes + few micro-climate sensors + free forecast + static
  sun-maps + coarse per-zone canopy + valves + the balance model. Location-portable (balcony →
  garden → Piedmont): build once, compounds.

## Data sources

- **ESP32 home-display server** (`SENSOR_API_URL=https://laptop.local:8000`, `X-Api-Key`):
  - Forecast/archive: `GET /openmeteo/weather?start_ts&end_ts` (api-key reachable as of 2026-06-08).
  - Sensors: `GET /sensors`, `/sensors/{id}/readings?start_ts&end_ts&max_points`, `/sensors/latest`.
- **Sensors:** SwitchBot temp/RH — **South** (railing, cool/exposed), **South wall** (hot/dry),
  **West** (chilli afternoon window); a **Bed** sensor is INDOOR (excluded). Xiaomi **Flower Care**
  soil probe in the Cilantro pot (`id 3ee7f8a3-…`): moisture / light / temp / EC — the
  ground-truth calibration anchor.
- **Scripts:** `water_demand.py` (VPD, ET₀, Kc), `forecast_et0.py` (live daily ET₀),
  `water_balance.py` (the join + per-species Kc), `soil_drydown.py` (the drydown/demand
  validation + depletion fit), `watering_detector.py` (supply events). All run in the backend
  container (where `laptop.local` resolves); `soil_drydown`/`water_demand` are numpy-free.

## Next steps

1. **Crack #2 — `rate = f(VPD, current-moisture, canopy)`.** Add the moisture-dependent slowdown
   (Ks) + the coarse canopy multiplier; expect R² to lift from 0.39. Needs more days / a less
   quantized soil signal than the FlowerCare %, and the canopy proxy wired in.
2. **Ground-`k` calibration** — `k` from the balcony pot won't transfer to ground beds (different
   soil profile/drainage/root depth); calibrate in ground. The *method* transfers, the constant doesn't.
3. **Predictive balance** — forecast `moisture(t)` per zone → "water zone X by Yh / by N mm".
4. **Close the loop** — auto-pump/valves as known input: `sense → dose → measure response → adjust`,
   learning each zone's demand curve and dosing ahead of the forecast.

## Constraints (from nursery.md)

- **Ground ≠ pot** — garden water physics differ (soil profile, drainage, root depth); many zones,
  sparse sensors; likely **off-grid / visited every few days** → power + water storage/pressure are
  site constraints.
- **No manual logs** — must self-bootstrap from the probe(s) + sensors + forecast + occasional
  coarse human corrections.
- **Under/over-watering is the #1 survival/quality risk**, worst on the warm-tender quality crops
  that are the edge — so per-zone dosing (not garden-average) preserves the quality story at scale.

## The goal

A **closed-loop irrigation controller** — the balcony is a working miniature of the 100 m² garden.
