#!/usr/bin/env python3
"""PROTOTYPE per-region sun/shade detector via a sky-exposed REFERENCE surface.

The breakthrough: per-region sun/shade is detectable, but only against a clean
reference. The cross-region average fails (it's contaminated by the shaded plants
themselves); a fixed SKY-EXPOSED surface that isn't shaded by the plants works.
Here that's the GLASS CANOPY ROOF just above the lemongrass — it tracks ambient
sky light. Method:

  per region, per frame:  r = log( region_brightness / roof_brightness )
  then per-region detrend (subtract the region's own time-mean) to remove its
  static albedo, leaving the TEMPORAL signal:  + = brighter-vs-sky = SUN,
  - = darker-vs-sky = SHADE.

Dividing by the roof cancels global lighting + auto-exposure (same frame, same
exposure); the per-region detrend cancels albedo. What survives is local sun/shade.

VALIDATED against human labels (2026-06-08, all times LOCAL = UTC+2):
  07:00 chillis SHADE -> -0.63/-0.71  (Hangijiao4/7)         OK
  10:00 chillis SUN   -> +0.34/+0.44                          OK (the dark-seedling
        case that brightness-diff and a colour-temp cue both MISSED)
  10:00 Moroccan SHADE-> -0.03 (marginal)                     ok
  11:00 road SUN      -> flips -0.22 -> +0.28 at 09Z (=11 local)  OK
  weak/known-bad: parsley (partial sun), car-spot (a MOVING CAR, not a surface).

CAVEATS:
  * the reference must be sky-exposed and NOT shaded by the plants (the roof works;
    the road/car-spot do not — the car moves);
  * the per-region SUN map drifts through the YEAR (sun geometry) -> re-run
    seasonally. (This is the value of auto-detecting vs hand-mapping once.)
  * PROTOTYPE: validated on a handful of labels over one morning; the per-region
    SUN-HOURS profile is the next build (full-day arc + several clear days).
See docs/ai-tagging-design.md.

    .venv/bin/python scripts/sun_shade.py 'data/photos/2026-06-08T0[4-9]*Z.jpg' 'data/photos/2026-06-08T100000Z.jpg'
"""
import os, sys, glob, argparse, json
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.frame_registration as fr
import scripts.finlayson_experiment as F

# Glass-canopy roof patch above the lemongrass (normalised x0,y0,x1,y1): sky-exposed.
ROOF = (0.06, 0.25, 0.20, 0.38)
REF_DEFAULT = "data/photos/2026-06-08T100000Z.jpg"


def gray_box(im, h, w, x0, y0, x1, y1):
    g = cv2.cvtColor(im[int(y0*h):int(y1*h), int(x0*w):int(x1*w)], cv2.COLOR_BGR2GRAY)
    return float(g.mean())


def region_b(im, h, w, r):
    x0, y0, x1, y1 = fr.norm_corners(r)
    return gray_box(im, h, w, max(0, x0-0.006), y0, x1+0.006, y1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", nargs="+")
    ap.add_argument("--ref", default=REF_DEFAULT)
    a = ap.parse_args()
    paths = sorted(sum((glob.glob(f) for f in a.frames), []))
    ref = cv2.imread(a.ref); h, w = ref.shape[:2]
    regs = {}
    for r in fr.load_regions():
        regs.setdefault(r["unit_id"], []).append(r)

    times, ratio = [], {u: [] for u in regs}
    for p in paths:
        try:
            c = json.load(open(p.replace(".jpg", ".json"))).get("camera")
        except FileNotFoundError:
            c = None
        im = cv2.imread(p)
        if os.path.abspath(p) != os.path.abspath(a.ref):
            res = fr.register_pair(fr.features_gray(ref), fr.features_gray(im))
            if res[0] is not None and fr.plausible(*res):
                im = cv2.warpAffine(im, res[0], (w, h))
        roof = gray_box(im, h, w, *ROOF)
        times.append(os.path.basename(p)[11:13])
        for u, rs in regs.items():
            ratio[u].append(np.mean([np.log((region_b(im, h, w, r) + 1) / (roof + 1)) for r in rs]))

    units = list(regs)
    M = np.array([ratio[u] for u in units])
    resid = M - M.mean(1, keepdims=True)        # per-region detrend removes albedo
    print("per-region sun/shade vs the roof reference;  + = SUN,  - = SHADE")
    print("times (UTC; +2 = local):  " + " ".join(f"{t:>5}" for t in times))
    for i, u in enumerate(units):
        print(f"{F.NAMES.get(u, str(u)):>16}  " + " ".join(f"{v:+5.2f}" for v in resid[i]))


if __name__ == "__main__":
    main()
