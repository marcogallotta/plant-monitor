#!/usr/bin/env python3
"""Multi-pair harvest-signal evaluation: register -> Finlayson illuminant-invariant
image -> per-region diff -> z-score each region against its OWN baseline built from
the other (no-harvest) pairs.

WHY A BASELINE, NOT A RANK: absolute region diff is driven by region size/texture
and hourly sun-angle change, not harvest (big leafy regions are always loud). A
harvest is a region departing from ITS OWN normal, so we score (val - median)/MAD
per region across many pairs and flag the outliers in the harvest window.

IMPORTANT — INPUT DATA: feed this BURST-AVERAGED PLATES (pi/capture.py, commit
aa74532), NOT single captures. Single frames carry full foliage sway (~60-69% more
per-region variation), which inflates the baseline noise floor and buries the
harvest. This script's verdict is only trustworthy on plate data; on single frames
it is a pessimistic lower bound.

Usage:
    .venv/bin/python scripts/harvest_eval.py --harvest 15->16 FRAME.jpg FRAME.jpg ...
    # frames are diffed as consecutive pairs in the order given (or sorted glob).
    .venv/bin/python scripts/harvest_eval.py --harvest 15->16 'data/photos/2026-06-07T*Z.jpg'
"""
import os, sys, glob, argparse
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.finlayson_experiment as F
import scripts.frame_registration as fr

HARVESTED = {"Genovese basil", "Rocket", "Dill"}  # known 2026-06-07 17:00-18:00 CEST


def theta_of(chi, valid):
    v = chi[valid][::7]
    best, bt = 1e18, 0.0
    for d in range(0, 180, 3):
        t = np.deg2rad(d)
        e = F._entropy(v[:, 0]*np.cos(t) + v[:, 1]*np.sin(t))
        if e < best:
            best, bt = e, t
    return bt


def pair_diffs(p0, p1, regs, half=True):
    ref, tgt = cv2.imread(p0), cv2.imread(p1)
    if half:
        ref = cv2.resize(ref, (ref.shape[1]//2, ref.shape[0]//2))
        tgt = cv2.resize(tgt, (tgt.shape[1]//2, tgt.shape[0]//2))
    res = fr.register_pair(fr.features_gray(ref), fr.features_gray(tgt))
    if res[0] is not None and fr.plausible(*res):
        h, w = ref.shape[:2]
        tgt = cv2.warpAffine(tgt, res[0], (w, h))
    cr, vr = F.log_chrom(ref)
    th = theta_of(cr, vr)
    Ir = F.invariant(cr, th)
    ct, _ = F.log_chrom(tgt)
    It = F.invariant(ct, th)
    out = {}
    for r in regs:
        a, b = F._crop(Ir, r), F._crop(It, r)
        if a is not None and b is not None and a.shape == b.shape:
            out.setdefault(r["unit_id"], []).append(float(np.abs(a-b).mean()))
    return {u: float(np.mean(v)) for u, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", nargs="+")
    ap.add_argument("--harvest", required=True, help="pair label e.g. 15->16")
    a = ap.parse_args()
    paths = sorted(sum((glob.glob(f) for f in a.frames), []))
    regs = fr.load_regions()

    pairs, mats = [], []
    for p0, p1 in zip(paths, paths[1:]):
        lbl = os.path.basename(p0)[11:13] + "->" + os.path.basename(p1)[11:13]
        pairs.append(lbl)
        mats.append(pair_diffs(p0, p1, regs))
    if a.harvest not in pairs:
        sys.exit(f"--harvest {a.harvest} not among pairs {pairs}")

    units = sorted(set().union(*[set(m) for m in mats]))
    M = np.array([[m.get(u, np.nan) for u in units] for m in mats])
    hi = pairs.index(a.harvest)

    print("max / mean rawINV per pair:")
    for i, l in enumerate(pairs):
        print(f"  {l}: max={np.nanmax(M[i]):5.1f} mean={np.nanmean(M[i]):5.1f}"
              f"{'  *** HARVEST' if i == hi else ''}")

    base = np.delete(M, hi, axis=0)
    med = np.nanmedian(base, axis=0)
    mad = np.nanmedian(np.abs(base - med), axis=0) + 1e-6
    z = (M[hi] - med) / (1.4826 * mad)
    print(f"\nper-region z-score in {a.harvest} vs own baseline (sorted):")
    for u, zz, val, mm in sorted(zip(units, z, M[hi], med), key=lambda x: -x[1]):
        nm = F.NAMES.get(u, u)
        mk = "  <== HARVESTED" if nm in HARVESTED else ""
        print(f"  {nm:>16}: z={zz:5.1f}  ({a.harvest}={val:4.1f}, base={mm:4.1f}){mk}")


if __name__ == "__main__":
    main()
