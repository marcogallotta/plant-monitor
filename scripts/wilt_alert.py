#!/usr/bin/env python3
"""PROTOTYPE wilt / water-stress detector — projected-greenness time series.

Wilt is GEOMETRY, not appearance. The literature (leaf-angle / leaf-tip motion /
canopy droop — LAX, Kinovea, image-based wilting metrics) is unanimous that wilting
is a structural/movement signal; an appearance-distance metric (gradINV) saturates
and detects nothing here. A drooping canopy shows LESS projected green from overhead
(folded, edge-on leaves expose less surface), so this tracks, per region, the
projected GREEN AREA and mean greenness over the day — a wilt is a transient MIDDAY
DIP that RECOVERS by evening.

Validated as the right FEATURE CLASS on 2026-06-07 (basil, exposed, wilted ~12Z):
green area dipped 0.85 -> 0.71 at 12-13Z and recovered to 0.84; shaded rocket ROSE
(no wilt), parsley flat. gradINV showed a flat ~0.9 for everything.

WHY PROTOTYPE / not production:
  * single-day signal is modest (~16-20%) and NOT cleanly separable from lighting-
    driven ExG swings (a confirmed wilt and an unconfirmed tarragon dip look similar);
  * normalised-rgb ExG still rides on AWB drift + shade-net dappling;
  * overhead is a poor angle for droop (foreshortened) — the closeup/LLM layer sees
    it natively and may be the better home for wilt confirmation.
The real detector needs a per-region MULTI-DAY DIURNAL BASELINE (each region's normal
greenness-by-hour) to flag a midday dip exceeding the region's own variation — the
plate-days now accruing feed exactly that. See docs/ai-tagging-design.md.

    .venv/bin/python scripts/wilt_alert.py 'data/photos/2026-06-07T0[7-9]*Z.jpg' 'data/photos/2026-06-07T1[0-5]*Z.jpg'
"""
import os, sys, glob, argparse
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.frame_registration as fr
import scripts.finlayson_experiment as F   # for NAMES only

EXG_THR = 0.15        # normalised-rgb ExG threshold for "green" (fixed, AWB-robust-ish)
DIP_FRAC = 0.12       # provisional: a midday dip >= this fraction of baseline = candidate
REF_DEFAULT = "data/photos/2026-06-07T130010Z.jpg"


def exg(bgr):
    """Normalised-rgb excess green (intensity removed; fixed threshold survives
    exposure changes better than raw)."""
    b = bgr.astype(np.float32); s = b.sum(2) + 1e-6
    return 2 * b[..., 1] / s - b[..., 2] / s - b[..., 0] / s


def green_area(e, r, w, h):
    x0, y0, x1, y1 = fr.norm_corners(r)
    cx0, cx1 = sorted((int(x0 * w), int(x1 * w)))
    cy0, cy1 = sorted((int(y0 * h), int(y1 * h)))
    sub = e[max(0, cy0):cy1, max(0, cx0):cx1]
    return float((sub > EXG_THR).mean()) if sub.size else np.nan


def build_series(frame_paths, ref_path):
    ref = cv2.imread(ref_path); h, w = ref.shape[:2]
    regs = {}
    for r in fr.load_regions():
        regs.setdefault(r["unit_id"], []).append(r)
    times, series = [], {u: [] for u in regs}
    for p in frame_paths:
        im = cv2.imread(p)
        if os.path.abspath(p) != os.path.abspath(ref_path):
            res = fr.register_pair(fr.features_gray(ref), fr.features_gray(im))
            if res[0] is not None and fr.plausible(*res):
                im = cv2.warpAffine(im, res[0], (w, h))
        e = exg(im)
        times.append(os.path.basename(p)[11:13])
        for u, rs in regs.items():
            series[u].append(float(np.nanmean([green_area(e, r, w, h) for r in rs])))
    return times, sorted(regs), series


def detect_wilt(s):
    """PROTOTYPE single-day rule: a transient midday DIP that recovers. The day's
    baseline is the morning+evening level (ends); a dip in the MIDDLE below
    baseline*(1-DIP_FRAC) that recovers near baseline = candidate wilt. The real
    version replaces 'baseline from the ends' with a multi-day diurnal baseline."""
    a = np.asarray(s, float)
    ok = ~np.isnan(a)
    if ok.sum() < 5:
        return None
    n = len(a)
    edge = np.nanmean(np.concatenate([a[:2], a[-2:]]))      # morning+evening baseline
    mid = a[2:n - 2]
    if mid.size == 0 or edge <= 0:
        return None
    lo = np.nanmin(mid); lo_i = 2 + int(np.nanargmin(mid))
    recovers = a[-1] >= edge * (1 - DIP_FRAC / 2)
    if (edge - lo) / edge >= DIP_FRAC and recovers:
        return {"dip_at": lo_i, "baseline": edge, "low": lo,
                "drop_pct": (edge - lo) / edge * 100}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", nargs="+")
    ap.add_argument("--ref", default=REF_DEFAULT)
    a = ap.parse_args()
    paths = sorted(sum((glob.glob(f) for f in a.frames), []))
    if len(paths) < 5:
        sys.exit("need >=5 frames for a daytime series")
    times, units, series = build_series(paths, a.ref)
    print("PROTOTYPE — green-area dip; single-day, thresholds provisional (see docstring)\n")
    print("frames: " + " ".join(times))
    flagged = []
    for u in units:
        w = detect_wilt(series[u])
        spark = " ".join(f"{v:4.2f}" if v == v else "  - " for v in series[u])
        tag = ""
        if w:
            tag = f"  <== WILT? -{w['drop_pct']:.0f}% at {times[w['dip_at']]}Z"
            flagged.append(F.NAMES.get(u, u))
        print(f"{F.NAMES.get(u, u):>16}  {spark}{tag}")
    print("\ncandidate wilts:", ", ".join(flagged) if flagged else "(none)")
    print("NOTE prototype: single-day green-area dip is modest and lighting-confounded; "
          "needs a per-region multi-day diurnal baseline to be trustworthy.")


if __name__ == "__main__":
    main()
