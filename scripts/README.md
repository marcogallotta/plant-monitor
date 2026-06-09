# scripts/ — index

Utility scripts, research prototypes, and the offline workers behind the
monitoring / irrigation / tagging work. For *why* any of this exists, see
[`../docs/roadmap.md`](../docs/roadmap.md) (entry point),
[`../docs/irrigation.md`](../docs/irrigation.md),
[`../docs/vision-tagging.md`](../docs/vision-tagging.md).

## How to run these (the practical bit)

- **Flat package.** Everything imports siblings as `import scripts.x`. Invoke as
  `python -m scripts.x` from the repo root, or `.venv/bin/python scripts/x.py`.
- **Two environments — pick the right one:**
  - **Host `.venv`** for anything needing **`cv2`** (image work) — `cv2` is NOT in
    the backend container. Most vision scripts run here.
  - **Backend container** for anything hitting the **DB or the esp32 server**
    (`laptop.local` only resolves there): `docker compose run --rm backend python scripts/x.py`.
    `water_demand.py`, `forecast_et0.py`, `water_balance.py`, `soil_drydown.py` are
    deliberately **numpy/cv2-free** so they run in the container.

## Foundation library — imported widely, do NOT relocate

Moving these breaks the import graph (import counts in parens).

| File | What | Notes |
|---|---|---|
| `frame_registration.py` | CLAHE + chained-ORB registration, `warp_region`, `load_regions`/`load_controls` | **the core** (×14) |
| `finlayson_experiment.py` | `NAMES` map, Finlayson illuminant-invariant, `_crop` | **a library despite the name** (×6) |
| `water_demand.py` | FAO-56 ET₀, VPD, Kc — pure math | numpy-free (×4) |
| `sun_shade.py` | per-region sun/shade via the sky-roof reference | (×2) |
| `stabilize_core.py` | offline frame-stabilization worker core | (×2) |

## Irrigation / water-balance (Track A)

| File | What | Status | Runs |
|---|---|---|---|
| `forecast_et0.py` | live daily ET₀ from Open-Meteo | tool | container |
| `water_balance.py` | per-plant join `ET₀ × Kc × sun-fraction` (+ per-species Kc) | tool/lib | anywhere |
| `water_balance_live.py` | live orchestration: glue sun_hours + ET₀ + VPD | tool | host (cv2) |
| `soil_drydown.py` | crack #1/#1b — drydown-vs-demand validation + depletion fit | tool | container |
| `watering_detector.py` | supply side — watering events from EC+moisture fusion | tool | container |
| `sun_hours.py` | per-region sun-hours profiler (the camera demand term) | **prototype** | host (cv2) |
| `insolation_validate.py` | radiometric insolation-from-camera, validated on open-sun | prototype | host (cv2) |
| `insolation_experiment.py` | naive insolation — **falsified** (−0.43); kept as evidence | prototype | host (cv2) |
| `aosta_station_temps.py` | Aosta weather-station temperature exploration | exploration | — |

## Vision / change detection (Track B research)

| File | What | Status | Runs |
|---|---|---|---|
| `export_reference_regions.py` | DB → `reference_regions.json` (plant + control tags) | tool | container |
| `harvest_eval.py` | time-series harvest/wilt detector (Finlayson invariant) | prototype | host (cv2) |
| `wilt_alert.py` | wilt detection (projected-greenness) | prototype | host (cv2) |
| `move_detect.py` | move detection — consecutive-frame colour; **not converged** | prototype | host (cv2) |
| `sway_experiment.py` | burst-plate sway-suppression validation | tool | host (cv2) |
| `lighting_experiment.py` | lighting-robust change-signal exploration | prototype | host (cv2) |

## Tagging pipeline (Track B) — PAUSED (roadmap Phase 3)

Built around the old contact-sheet approach; see vision-tagging.md "smoking guns"
before reusing. `ingest_suggestions.py` (the review-workflow ingest) is the part
that is **live**, not paused.

| File | What |
|---|---|
| `ingest_suggestions.py` | **live** — ingest AI suggestions → review workflow |
| `prepare_tagging_run.py` | session-grouping for a batch run |
| `submit_tagging_batch.py` / `ingest_tagging_batch.py` | Batch-API submit / ingest |
| `agreement_gate.py` | Sonnet-vs-Opus agreement triage |
| `compare_ab_runs.py` | A/B prior comparison |
| `triage_plant.py` | per-plant triage helper |

## Stabilizer worker (operational)

`stabilize_core.py` (core), `compute_stabilization.py` (CLI),
`plant-stabilize.service` / `.timer`, `media-shared.service` (systemd units).

## One-off migrations — DONE (kept for reference)

`fix_timestamps.py`, `fix_content_hashes.py`, `seed.py`.

## Tests

`test_frame_registration.py`, `test_stabilization.py`, `test_water_balance.py`,
`test_water_demand.py`. Run e.g. `.venv/bin/python -m scripts.test_water_demand`.

## Fixtures

`reference_regions.json` (region+control tags on the reference frame — regenerate
with `export_reference_regions.py`), `testdata/` (registration fixtures).

## Throwaway — safe to delete

`_idtest_sample.py`, `_idtest_key.txt` (blind ID-test leftovers; `_idtest_key.txt`
is root-owned → needs `sudo rm`).

---

**Possible future tidy (deferred on purpose):** a `research/` subdir for the
leaf prototypes would be cleaner, but the flat `scripts.x` import graph + per-file
`sys.path` depth make physical moves a real refactor (update imports, run commands,
docstrings). Not worth the risk for cosmetics — do it deliberately if/when this
gets packaged properly. This index gives the navigability without the breakage.
