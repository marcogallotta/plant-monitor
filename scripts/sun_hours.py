#!/usr/bin/env python3
"""Per-region SUN-HOURS profile — the per-plant DEMAND term for the water model.

Integrates the per-frame sun/shade signal (scripts/sun_shade.py) over a day's
arc into HOURS OF DIRECT SUN per region, then averages across clear days into a
stable per-region, per-hour insolation profile.

Method (per day, reusing the validated sun_shade reference trick):
  per region, per frame:  r = log(region_brightness / roof_brightness)   [sky ref]
  per-region detrend (subtract that region's day-mean) -> + = SUN, - = SHADE
  classify each frame sun/shade by sign (deadband = --thr)
  weight each frame by the time to the next frame
    -> SUN-HOURS = sum of the sunny frames' durations.
Across days: average the per-(region, local-hour) sun fraction -> expected
sun-hours/day and the hourly arc. Several CLEAR days are needed for a trusted
profile (cloud scrambles a single day); the map also drifts with sun geometry,
so RE-RUN SEASONALLY. That seasonal re-run is exactly why this auto-detects
rather than hand-maps once.

PROTOTYPE / preliminary: validated tooling, but the standing profile needs the
full daytime arc (frames still accrue past midday) over multiple clear days.
See docs/ai-tagging-design.md ("per-region sun/shade", "water-balance estimator").

  .venv/bin/python scripts/sun_hours.py 'data/photos/2026-06-08T*Z.jpg'
  .venv/bin/python scripts/sun_hours.py 'data/photos/2026-06-0[678]T*Z.jpg'   # multi-day
"""
import os, sys, glob, argparse, json
from datetime import datetime
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.frame_registration as fr
import scripts.finlayson_experiment as F
import scripts.sun_shade as ss

UTC_OFFSET_H = 2          # CEST = UTC+2; frame filenames are UTC, Marco speaks local
TS_FMT = "%Y-%m-%dT%H%M%SZ"
# Only PERMANENT-SHADE controls estimate the reference error: a surface that
# never sees direct beam moves only with roof/exposure leak. Sun-exposed controls
# (road, wall, sign) catch the real midday sun and would subtract it from plants.
SHADE_CONTROL_MATCH = "always shad"
# Frames are warped to the reference, so their EDGES catch black border / off-scene
# pixels — a control touching the edge is noisy garbage (verified: a frame-edge
# shade strip ran 2x the dev-std of an interior one). Reject controls within this
# normalised margin of any side.
EDGE_MARGIN = 0.02


def _interior(c):
    x0, y0, x1, y1 = fr.norm_corners(c)
    return x0 > EDGE_MARGIN and y0 > EDGE_MARGIN and x1 < 1 - EDGE_MARGIN and y1 < 1 - EDGE_MARGIN


def frame_time(path):
    return datetime.strptime(os.path.basename(path)[:18], TS_FMT)


def is_daylight(path, min_lux):
    """Gate out night/twilight — the per-region detrend is meaningless once the
    whole scene is dark (uniform darkness reads as noise the sign-test then
    miscalls 'sun'). The capture's own lux meter separates cleanly here (night
    ~0.3, day >=177). Falls back to exposure*gain when lux is absent, and lets a
    frame through (with no gate) when it carries no camera metadata at all
    (pre-2026-06-07 frames) — those days just shouldn't be trusted for a profile.
    """
    try:
        c = json.load(open(path.replace(".jpg", ".json"))).get("camera") or {}
    except (FileNotFoundError, ValueError):
        return True
    if "lux" in c:
        return c["lux"] >= min_lux
    eg = c.get("exposure_us", 0) * c.get("analogue_gain", 0) * c.get("digital_gain", 1)
    return eg < 5e5 if eg else True


def frame_durations_h(times):
    """Hours each frame represents = gap to the next frame (last reuses the
    median gap). Robust to the irregular ~hourly cadence and missing frames."""
    secs = [(times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)]
    med = float(np.median(secs)) if secs else 3600.0
    return [(s / 3600.0) for s in secs] + [med / 3600.0]


def region_logratios(paths, ref, ref_path, w, h, regs, controls=()):
    """Per-frame log(region/roof), registering each frame to ref ONCE. Returns
    (times, {unit_id: [logratio]}, [[control logratio per frame] per control])."""
    times, ratio, cratio = [], {u: [] for u in regs}, [[] for _ in controls]
    for p in sorted(paths):
        im = cv2.imread(p)
        if os.path.abspath(p) != os.path.abspath(ref_path):
            M, inl, good = fr.register_pair(fr.features_gray(ref), fr.features_gray(im))
            if M is not None and fr.plausible(M, inl, good):
                im = cv2.warpAffine(im, M, (w, h))
        roof = ss.gray_box(im, h, w, *ss.ROOF)
        times.append(frame_time(p))
        for u, rs in regs.items():
            ratio[u].append(np.mean([np.log((ss.region_b(im, h, w, r) + 1) / (roof + 1)) for r in rs]))
        for j, c in enumerate(controls):
            cratio[j].append(float(np.log((ss.region_b(im, h, w, c) + 1) / (roof + 1))))
    return times, ratio, cratio


def sun_hours_for_day(paths, ref, ref_path, w, h, regs, controls, margin, base_pct, common_mode):
    """-> (times, {uid: signal above own shade baseline}, {uid: sun_hours}, global_resid).

    Per region, the absolute log(region/roof) is exposure- and ambient-cancelled
    (roof = sky reference, same frame). We do NOT detrend by the region's MEAN
    (that forces ~50% sun and discards the very level we want); instead each
    region's SHADE BASELINE is its low percentile (its value when shaded) and a
    frame counts as sun when it rises `margin` (log units) above that baseline.
    Albedo cancels (baseline is per-region) without flattening the absolute
    sun-vs-shade level, so a full-sun pot reads ~all-day and a deep-shade pot
    reads ~none — the cross-region difference the demand term needs.

    The residual per-frame global reference error (single-roof-patch leak) is
    estimated from the FIXED NON-PLANT CONTROLS, not the plant cohort: the shared
    component across the controls (their median deviation from their own
    baselines) is the leak, while a real broad sun-sweep across PLANTS survives
    because the controls don't move with it. `--common-mode` falls back to the
    old plant-cohort estimate (cleans the leak but eats a real sweep); no controls
    and no `--common-mode` leaves the signal uncorrected.
    """
    times, ratio, cratio = region_logratios(paths, ref, ref_path, w, h, regs, controls)
    dur = frame_durations_h(times)
    units = list(regs)
    M = np.array([ratio[u] for u in units])
    if controls and not common_mode:
        # Permanent-shade controls never see sun, so MEAN-centre (signed): the
        # deviation is pure reference error, +/- around the patch's own level.
        C = np.array(cratio)                                       # [n_controls, n_frames]
        global_resid = np.median(C - C.mean(axis=1, keepdims=True), axis=0)
    elif common_mode:
        global_resid = np.median(M - np.percentile(M, base_pct, axis=1, keepdims=True), axis=0)
    else:
        global_resid = np.zeros(M.shape[1])
    baseline = np.percentile(M, base_pct, axis=1, keepdims=True)   # per-region shaded level
    above = (M - baseline) - global_resid[None, :]                 # sun when > margin
    out_above, out_hours = {}, {}
    for i, u in enumerate(units):
        sun = above[i] > margin
        out_above[u] = above[i]
        out_hours[u] = float(sum(d for d, s in zip(dur, sun) if s))
    return times, out_above, out_hours, global_resid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", nargs="+")
    ap.add_argument("--ref", default=ss.REF_DEFAULT)
    ap.add_argument("--margin", type=float, default=0.15,
                    help="sun if log(region/roof) rises >margin above the region's "
                         "shade baseline (log units; default 0.15)")
    ap.add_argument("--base-pct", type=float, default=25.0,
                    help="percentile defining each region's shade baseline (default 25)")
    ap.add_argument("--min-lux", type=float, default=50.0,
                    help="daylight gate: drop frames dimmer than this (default 50)")
    ap.add_argument("--controls", action="store_true",
                    help="subtract a global residual estimated from the PERMANENT-"
                         "SHADE control(s) (label ~ 'always shaded') — the clean "
                         "reference-error estimator (experimental; the patch is a "
                         "narrow strip, so n=1 is noisy)")
    ap.add_argument("--common-mode", action="store_true",
                    help="estimate the global residual from the plant cohort instead "
                         "(cleans roof noise but eats a broad sun-sweep; experimental)")
    a = ap.parse_args()
    paths = sorted(sum((glob.glob(f) for f in a.frames), []))
    if not paths:
        sys.exit("no frames matched")
    n_all = len(paths)
    paths = [p for p in paths if is_daylight(p, a.min_lux)]
    if not paths:
        sys.exit("no daylight frames after the lux gate")
    if len(paths) < n_all:
        print(f"[daylight gate: kept {len(paths)}/{n_all} frames "
              f"(dropped night/twilight, lux<{a.min_lux:g})]")
    ref = cv2.imread(a.ref); h, w = ref.shape[:2]
    regs = {}
    for r in fr.load_regions():
        regs.setdefault(r["unit_id"], []).append(r)

    # Permanent-shade control(s) estimate the reference error. Default OFF: on the
    # one validated day the broad morning-shade->midday-sun sweep is REAL (the whole
    # balcony is building-shaded at dawn), so raw per-region shade-baseline (no
    # residual) is validated-consistent.
    controls = [c for c in fr.load_controls()
                if SHADE_CONTROL_MATCH in c["label"].lower() and _interior(c)] if a.controls else []
    if a.common_mode:
        print("[global residual: plant-cohort common-mode (--common-mode, experimental)]")
    elif a.controls and controls:
        print(f"[global residual: {len(controls)} permanent-shade control(s) "
              f"(experimental, narrow strip) -> " + ", ".join(c["label"] for c in controls) + "]")
    elif a.controls:
        print(f"[--controls: no control labelled '{SHADE_CONTROL_MATCH}*' found; "
              "falling back to raw shade baseline]")
    else:
        print("[global residual: none (raw per-region shade baseline; "
              "--controls / --common-mode to experiment)]")

    # group by calendar date (UTC) -> a day = one arc to integrate
    days = {}
    for p in paths:
        days.setdefault(os.path.basename(p)[:10], []).append(p)

    units = list(regs)
    per_day_hours = {u: [] for u in units}            # sun-hours per clear day
    hour_sun = {u: {} for u in units}                 # local-hour -> [0/1] across days
    for d in sorted(days):
        times, above, hours, _ = sun_hours_for_day(
            days[d], ref, a.ref, w, h, regs, controls, a.margin, a.base_pct, a.common_mode)
        lhours = [(t.hour + UTC_OFFSET_H) % 24 for t in times]
        span = (times[-1] - times[0]).total_seconds() / 3600.0
        print(f"\n=== {d}  ({len(times)} frames, "
              f"{lhours[0]:02d}:00->{lhours[-1]:02d}:00 local, {span:.1f}h arc) ===")
        print("region            sun-h  " + " ".join(f"{lh:>2d}" for lh in lhours))
        for u in sorted(units, key=lambda u: -hours[u]):
            mark = "".join(" ●" if v > a.margin else " ·" for v in above[u])
            print(f"{F.NAMES.get(u, str(u)):>16} {hours[u]:5.1f} {mark}")
            per_day_hours[u].append(hours[u])
            for lh, v in zip(lhours, above[u]):
                hour_sun[u].setdefault(lh, []).append(1 if v > a.margin else 0)

    if len(days) > 1:
        print(f"\n=== profile across {len(days)} days (mean sun-hours/day) ===")
        for u in sorted(units, key=lambda u: -np.mean(per_day_hours[u])):
            print(f"{F.NAMES.get(u, str(u)):>16} {np.mean(per_day_hours[u]):5.1f} "
                  f"(+/-{np.std(per_day_hours[u]):.1f})")
    else:
        print("\n[single day — preliminary; a trusted profile needs several CLEAR "
              "days + the full daytime arc. Re-run seasonally.]")


if __name__ == "__main__":
    main()
