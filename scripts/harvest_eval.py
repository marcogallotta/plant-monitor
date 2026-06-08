#!/usr/bin/env python3
"""Per-region TIME-SERIES harvest/wilt detector (supersedes the pairwise version).

Governing principle (docs/ai-tagging-design.md): a single before/after pair is the
wrong primitive — a 50 g harvest is near-invisible in one noisy pair but obvious in
the SEQUENCE ("flat, flat, flat, step, stays down"). So per region we build a time
series and look for a PERSISTENT STEP, which also separates the two confounds the
pair-diff couldn't:

  * HARVEST = a step that HOLDS to the end of the series (permanent mass loss).
  * WILT    = a transient excursion that RETURNS to baseline (turgor recovers).
  * lighting / sway = bounded noise the series sees through (judged vs each
    region's OWN median/MAD, not vs another region or another single frame).

Feature: one Finlayson illuminant-invariant projection (theta calibrated once on
the reference, applied to every frame so the space is consistent) -> per region,
per frame, the invariant distance to the reference region. That series is what the
change-point runs on.

Validation handle: yesterday's 2026-06-07 frames carry BOTH a known harvest
(Genovese basil + Rocket + Dill, 15:00Z->16:00Z, holds to 17Z) AND a known midday
wilt (exposed basil ~12Z, recovers) — so this is testable on real labelled data
even before plate-bracketed data exists.

    .venv/bin/python scripts/harvest_eval.py 'data/photos/2026-06-07T*Z.jpg'
"""
import os, sys, glob, argparse
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.finlayson_experiment as F
import scripts.frame_registration as fr

NAMES = F.NAMES
HARVESTED = {"Genovese basil", "Rocket", "Dill"}   # known 2026-06-07 harvest
REF_DEFAULT = "data/photos/2026-06-07T130010Z.jpg"


# --- per-region invariant-distance time series -----------------------------

def build_series(frame_paths, ref_path):
    """Return (times, units, S) where S[unit] = list of rawINV distance-to-
    reference over the frames (one Finlayson theta for the whole series)."""
    ref = cv2.imread(ref_path); h, w = ref.shape[:2]
    cr, vr = F.log_chrom(ref)
    theta = _theta_fast(cr, vr)          # subsampled entropy-min (fast over a series)
    Ir = F.invariant(cr, theta)

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
        ct, _ = F.log_chrom(im)
        It = F.invariant(ct, theta)
        times.append(os.path.basename(p)[11:13] + ":00Z")
        for u, rs in regs.items():
            ds = []
            for r in rs:
                a, b = F._crop(Ir, r), F._crop(It, r)
                if a is not None and b is not None and a.shape == b.shape:
                    ds.append(float(np.abs(a - b).mean()))
            series[u].append(float(np.mean(ds)) if ds else np.nan)
    return times, sorted(regs), series


def _theta_fast(chi, valid):
    v = chi[valid][::7]
    best, bt = 1e18, 0.0
    for d in range(0, 180, 3):
        t = np.deg2rad(d)
        e = F._entropy(v[:, 0] * np.cos(t) + v[:, 1] * np.sin(t))
        if e < best:
            best, bt = e, t
    return bt


# --- change-point: persistent step vs transient excursion ------------------

def classify_series(s, k_sigma=3.0, min_run=2):
    """Classify a per-region (common-mode-detrended) distance series.

    Returns dict(kind, score, step_at). `kind`:
      'harvest' — a sustained elevated run that HOLDS at the END of the series
                  (>= min_run frames); a permanent step. Isolated earlier blips
                  (e.g. a morning lighting artifact) are ignored — only the
                  persistent tail counts.
      'wilt'    — an elevated excursion that RETURNS to baseline before the end.
      'none'    — nothing exceeds the region's own noise.
    Score = elevation magnitude in units of the region's own MAD (robust).
    """
    s = np.asarray(s, float)
    ok = ~np.isnan(s)
    if ok.sum() < 4:
        return {"kind": "none", "score": 0.0, "step_at": None}
    base = np.nanmedian(s)
    mad = np.nanmedian(np.abs(s[ok] - base)) * 1.4826 + 1e-6
    thr = base + k_sigma * mad
    elev = ok & (s > thr)
    if not elev.any():
        return {"kind": "none", "score": 0.0, "step_at": None}

    n = len(s)
    if elev[-1]:                                  # elevation holds at the end
        i = n - 1
        while i >= 0 and elev[i]:                 # walk back over the tail run
            i -= 1
        run_start = i + 1
        if n - run_start >= min_run:              # sustained -> harvest
            mag = (np.nanmean(s[run_start:]) - base) / mad
            return {"kind": "harvest", "score": float(mag), "step_at": int(run_start)}
    # elevation that doesn't hold to the end (or too short) -> transient = wilt
    peak = np.nanmax(s[elev])
    return {"kind": "wilt", "score": float((peak - base) / mad),
            "step_at": int(np.where(elev)[0].min())}


# --- driver ----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", nargs="+", help="frame glob(s), chronological")
    ap.add_argument("--ref", default=REF_DEFAULT)
    ap.add_argument("--k-sigma", type=float, default=3.0)
    a = ap.parse_args()
    paths = sorted(sum((glob.glob(f) for f in a.frames), []))
    if len(paths) < 4:
        sys.exit("need >=4 frames for a series")

    times, units, series = build_series(paths, a.ref)
    print("frames:", " ".join(times), f"  (ref={os.path.basename(a.ref)[11:13]}:00Z)\n")

    # COMMON-MODE detrend: the diurnal lighting/exposure moves every region
    # together, so the per-frame median across regions IS the shared lighting
    # state. Subtracting it cancels the diurnal swing and leaves each region's
    # idiosyncratic change — a harvest is a region diverging ABOVE the scene's
    # common mode and holding. (Robust to a few harvested regions; breaks only if
    # most regions change at once.) This is the single-day stand-in for the
    # multi-day per-region diurnal baseline.
    M = np.array([series[u] for u in units], float)        # units x frames
    common = np.nanmedian(M, axis=0)                        # shared lighting per frame
    resid = {u: list(np.array(series[u], float) - common) for u in units}

    rows = []
    for u in units:
        c = classify_series(resid[u], a.k_sigma)
        rows.append((u, c, resid[u]))
    # harvest candidates first (by score), then wilts, then none
    order = {"harvest": 0, "wilt": 1, "none": 2}
    rows.sort(key=lambda r: (order[r[1]["kind"]], -r[1]["score"]))

    print(f"{'unit':>16}  {'verdict':>8} {'score':>5} {'step':>5}   series (distance-to-ref)")
    for u, c, s in rows:
        if c["kind"] == "none" and c["score"] == 0:
            continue
        nm = NAMES.get(u, str(u))
        step = times[c["step_at"]] if c["step_at"] is not None else "-"
        spark = " ".join(f"{v:4.0f}" if v == v else "  - " for v in s)
        mk = " <==HARVESTED" if nm in HARVESTED and c["kind"] == "harvest" else ""
        print(f"{nm:>16}  {c['kind']:>8} {c['score']:5.1f} {step:>5}   {spark}{mk}")

    print("\nharvest = elevated run that HOLDS to the last frame; "
          "wilt = excursion that RETURNS.")
    hits = [NAMES.get(u) for u, c, _ in rows if c["kind"] == "harvest"]
    print("flagged harvests:", ", ".join(hits) if hits else "(none)")


if __name__ == "__main__":
    main()
