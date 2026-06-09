#!/usr/bin/env python3
"""LIVE per-plant water-balance run — the orchestration that glues the three
demand inputs into a real per-plant demand table for a given day.

Cross-environment by necessity: this runs on the HOST (needs cv2 + the frames for
sun_hours), while ET0 and the sensor readings come from the backend container
(where laptop.local resolves). So fetch those two there and pass them in:

    # in the container:
    docker compose run --rm backend python scripts/forecast_et0.py            # -> ET0
    docker compose exec -T backend python -c "from app.sensors import get_state; print(get_state().latest())"

    # then on the host:
    .venv/bin/python scripts/water_balance_live.py --et0 5.42 \
        --sensors 'South=28.9/36,West=36.6/26,South wall=30.2/33'

sun_fraction = per-region sun-hours / the captured daylight arc (so it's the
fraction of OBSERVED daylight in direct sun). Partial arc ⇒ preliminary — the
full-day arc completes in the evening. Chillis use the West sensor (their
sun-driven afternoon move; their overhead tag only covers the morning — see
docs/vision-tagging.md). Demand = ET0 × Kc × sun_fraction.
"""
import os, sys, glob, argparse
import cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.sun_hours as sh
import scripts.water_balance as wb
import scripts.frame_registration as fr
import scripts.finlayson_experiment as F


def parse_sensors(spec):
    """'South=28.9/36,West=36.6/26' -> {name: vpd_kpa} via water_demand.vpd."""
    out = {}
    for part in spec.split(","):
        name, tr = part.rsplit("=", 1)
        t, rh = tr.split("/")
        out[name.strip()] = wb.wd.vpd(float(t), float(rh))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--et0", type=float, required=True, help="ET0 mm/day (forecast_et0.py)")
    ap.add_argument("--sensors", required=True,
                    help="per-sensor 'name=T/RH' list, e.g. 'South=28.9/36,West=36.6/26'")
    ap.add_argument("--frames", default="data/photos/2026-06-08T*Z.jpg")
    ap.add_argument("--ref", default=sh.ss.REF_DEFAULT)
    ap.add_argument("--margin", type=float, default=0.15)
    ap.add_argument("--base-pct", type=float, default=25.0)
    ap.add_argument("--min-lux", type=float, default=50.0)
    a = ap.parse_args()

    vpd_by_sensor = parse_sensors(a.sensors)
    paths = [p for p in sorted(glob.glob(a.frames)) if sh.is_daylight(p, a.min_lux)]
    if not paths:
        sys.exit("no daylight frames matched")
    ref = cv2.imread(a.ref); h, w = ref.shape[:2]
    regs = {}
    for r in fr.load_regions():
        regs.setdefault(r["unit_id"], []).append(r)

    times, _above, hours, _ = sh.sun_hours_for_day(
        paths, ref, a.ref, w, h, regs, [], a.margin, a.base_pct, False)
    # Denominator must be the SAME per-frame durations the numerator sums (each frame =
    # gap to the next, last reuses the median), NOT the bare first→last span: the span
    # omits the last frame's duration, so dividing by it inflates the fraction past 1.0.
    observed_h = sum(sh.frame_durations_h(times))
    arc_h = (times[-1] - times[0]).total_seconds() / 3600.0
    names = {u: F.NAMES.get(u, str(u)) for u in regs}
    sun_fraction = {u: min(1.0, hours[u] / observed_h) for u in regs}
    kc_by_unit = {u: wb.kc_for_name(names[u]) for u in regs}

    rows = wb.assemble(a.et0, sun_fraction, vpd_by_sensor, kc_by_unit, names)
    lh0, lh1 = (times[0].hour + sh.UTC_OFFSET_H) % 24, (times[-1].hour + sh.UTC_OFFSET_H) % 24
    print(f"LIVE per-plant water demand — ET0={a.et0:.1f} mm/day, arc {lh0:02d}:00-{lh1:02d}:00 "
          f"local ({arc_h:.0f}h, PRELIMINARY: partial day)")
    print("VPD by sensor: " + ", ".join(f"{k} {v:.1f}" for k, v in vpd_by_sensor.items()) + " kPa")
    print(f"{'plant':<16}{'Kc':>5}{'sun':>6}{'sensor':>11}{'VPD':>6}{'demand':>8}")
    print(f"{'':16}{'':>5}{'frac':>6}{'':>11}{'kPa':>6}{'mm/d':>8}")
    for r in rows:
        flag = "  <- stress" if r["stress"] else ""
        v = f"{r['vpd_kpa']:.1f}" if r["vpd_kpa"] is not None else "  ?"
        print(f"{r['name']:<16}{r['kc']:>5.1f}{r['sun_fraction']:>6.2f}{r['sensor']:>11}"
              f"{v:>6}{r['demand_mm']:>8.2f}{flag}")


if __name__ == "__main__":
    main()
