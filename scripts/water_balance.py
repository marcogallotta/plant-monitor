#!/usr/bin/env python3
"""Per-plant water-balance JOIN — combine the demand-side pieces into a daily
per-plant water demand + a heat-stress flag. This is "the join" (the last open
step of the demand side; see docs/ai-tagging-design.md "Demand side").

  demand_mm[unit] = ET0            (forecast — scripts/forecast_et0.py)
                  × Kc            (per-species crop coefficient, FAO-56 Table 12)
                  × sun_fraction  (camera — scripts/sun_hours.py: sun-hours / daylight-hours)
  vpd[unit]       = VPD of the unit's nearest micro-climate sensor (scripts/water_demand.py)

PURE join: fed the three precomputed inputs, so it runs anywhere — the inputs
come from different environments (sun_hours on the host with cv2; ET0/VPD from
the backend container where laptop.local resolves). cv2-free, stdlib + water_demand.
The CLI runs a worked demo on example numbers; pass --sun-json / --et0 / --vpd-json
to drive it on live data.

PROVISIONAL mappings (no in-frame sensor positions yet — fill when known):
  REGION→SENSOR: chillis (units 34/35/36) → West (their afternoon, high-demand
    spot); everything else → South (the railing) as a placeholder.
  Kc: leafy-herb ~1.0 across the board (FAO-56 Table 12 mid-season herbs).
"""
import os, sys, json, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.water_demand as wd

# Chillis are SUN-CHASED: their morning spot (the overhead tags) loses sun ~15:00,
# so they're moved to the West window for the afternoon. Their overhead sun-fraction
# is only valid pre-move; afternoon insolation ~= full sun at the West window, VPD
# from the West sensor. region->sensor for chillis switches at CHILLI_MOVE_HOUR.
CHILLI_UNITS = {34, 35, 36}
CHILLI_MOVE_HOUR = 15              # local hour they move to the West window
DEFAULT_SENSOR = "South"            # railing, placeholder for non-chilli pots
CHILLI_SENSOR = "West"
KC_DEFAULT = 1.0                    # leafy herbs, FAO-56 mid-season (provisional)
KC_BY_NAME = {}                    # per-species overrides go here when calibrated
VPD_STRESS_KPA = 2.5               # above this = high evaporative stress (flag, not action)


def unit_sensor(unit_id: int) -> str:
    """Nearest micro-climate sensor for a unit (provisional; time-collapsed to the
    afternoon high-demand window for movable chillis)."""
    return CHILLI_SENSOR if unit_id in CHILLI_UNITS else DEFAULT_SENSOR


def assemble(et0_mm, sun_fraction, vpd_by_sensor, kc_by_unit=None, names=None):
    """-> list of per-unit rows sorted by demand desc. Inputs:
      et0_mm          reference ET0 for the day (scalar)
      sun_fraction    {unit_id: 0..1}  (camera sun-hours / daylight-hours)
      vpd_by_sensor   {sensor_name: kPa}
      kc_by_unit      {unit_id: Kc}    (optional; defaults to KC_DEFAULT)
      names           {unit_id: label} (optional, for display)
    """
    kc_by_unit = kc_by_unit or {}
    names = names or {}
    rows = []
    for uid, sun in sun_fraction.items():
        sensor = unit_sensor(uid)
        vpd = vpd_by_sensor.get(sensor)
        kc = kc_by_unit.get(uid, KC_DEFAULT)
        rows.append({
            "unit_id": uid,
            "name": names.get(uid, str(uid)),
            "kc": kc,
            "sun_fraction": sun,
            "sensor": sensor,
            "vpd_kpa": vpd,
            "demand_mm": wd.plant_demand_mm(et0_mm, kc, sun),
            "stress": (vpd is not None and vpd >= VPD_STRESS_KPA),
        })
    return sorted(rows, key=lambda r: -r["demand_mm"])


def _demo_inputs():
    et0 = 5.4                                                    # today's forecast ET0
    vpd = {"South wall": 3.6, "South": 2.7, "West": 3.1}        # live-ish sensor VPDs
    # A few units with example camera sun-fractions + names.
    sun = {39: 0.9, 4: 0.5, 16: 0.3, 34: 0.7, 35: 0.6, 36: 0.4}
    names = {39: "Chives", 4: "Dill", 16: "Genovese basil",
             34: "Hangijiao4", 35: "Hangijiao7", 36: "Birdseye"}
    return et0, sun, vpd, names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--et0", type=float, help="reference ET0 mm/day (else demo value)")
    ap.add_argument("--sun-json", help="JSON file {unit_id: sun_fraction} from sun_hours")
    ap.add_argument("--vpd-json", help="JSON file {sensor_name: vpd_kpa}")
    a = ap.parse_args()

    et0, sun, vpd, names = _demo_inputs()
    live = a.sun_json or a.vpd_json or a.et0 is not None
    if a.et0 is not None:
        et0 = a.et0
    if a.sun_json:
        sun = {int(k): v for k, v in json.load(open(a.sun_json)).items()}
        names = {}
    if a.vpd_json:
        vpd = json.load(open(a.vpd_json))
    if not live:
        print("[DEMO inputs — pass --et0/--sun-json/--vpd-json for live data]")

    rows = assemble(et0, sun, vpd, names=names)
    print(f"per-plant daily water demand  (ET0={et0:.1f} mm, Kc={KC_DEFAULT} provisional)")
    print(f"{'unit':<16}{'sun':>5}{'sensor':>11}{'VPD':>6}{'demand':>8}")
    print(f"{'':16}{'frac':>5}{'':>11}{'kPa':>6}{'mm/d':>8}")
    for r in rows:
        flag = "  <- stress" if r["stress"] else ""
        v = f"{r['vpd_kpa']:.1f}" if r["vpd_kpa"] is not None else "  ?"
        print(f"{r['name']:<16}{r['sun_fraction']:>5.2f}{r['sensor']:>11}"
              f"{v:>6}{r['demand_mm']:>8.2f}{flag}")


if __name__ == "__main__":
    main()
