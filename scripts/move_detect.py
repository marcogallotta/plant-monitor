#!/usr/bin/env python3
"""Per-region MOVE detector — spot when a pot is relocated (no manual logging).

Generalises the chilli sun-chase: ANY pot can move, the user won't log it, so the
camera must detect it. A move is a per-region change-point like harvest/wilt, but a
DIFFERENT feature class:

  * harvest/wilt = canopy reflectance/texture change  -> the Finlayson invariant
    (scripts/harvest_eval.py) is the right feature.
  * MOVE = a whole pot leaves/arrives -> a big STRUCTURAL / intensity change (the
    pot's edges, shape, shadow vanish, revealing flat background). Validated on the
    known 2026-06-08 chilli move: morning = 3 pots+seedlings, 17:00 = bare tile.
    The invariant MISSED it (terracotta-on-bark vs beige-tile are similar chroma);
    a raw-grayscale structural diff catches it. So move uses raw gray, not invariant.

Per region: raw-gray mean-abs-diff to a MORNING reference, registered, daylight-
gated, common-mode detrended (shared lighting), then a persistent-step test
(reuse harvest_eval.classify_series): a move = a large step that HOLDS.

    .venv/bin/python scripts/move_detect.py 'data/photos/2026-06-08T*Z.jpg'
"""
import os, sys, glob, argparse
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.frame_registration as fr
import scripts.finlayson_experiment as F
import scripts.sun_hours as sh
import scripts.harvest_eval as he

CHILLI_UNITS = {34, 35, 36}        # known 2026-06-08 move — validation handle


def gray_series(paths, ref_path):
    """Per region, raw-gray mean-abs-diff to the reference region over the frames."""
    ref = cv2.imread(ref_path); h, w = ref.shape[:2]
    gref = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY).astype(np.float32)
    regs = {}
    for r in fr.load_regions():
        regs.setdefault(r["unit_id"], []).append(r)

    times, series = [], {u: [] for u in regs}
    for p in paths:
        im = cv2.imread(p)
        if os.path.abspath(p) != os.path.abspath(ref_path):
            # CHAINED registration (hourly hops) — direct fails across the day's
            # time span (the doc: a 3-4h shadow shift breaks ORB; hops compose).
            res = fr.register_to_reference(p, ref_path)
            if res["M"] is not None:
                im = cv2.warpAffine(im, res["M"], (w, h))
        g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
        times.append((sh.frame_time(p).hour + sh.UTC_OFFSET_H) % 24)
        for u, rs in regs.items():
            ds = []
            for r in rs:
                a, b = F._crop(gref, r), F._crop(g, r)
                if a is not None and b is not None and a.shape == b.shape:
                    ds.append(float(np.abs(a - b).mean()))
            series[u].append(float(np.mean(ds)) if ds else np.nan)
    return times, sorted(regs), series


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", nargs="+")
    ap.add_argument("--ref", help="morning reference frame (default: first daylight frame)")
    ap.add_argument("--min-lux", type=float, default=50.0)
    ap.add_argument("--k-sigma", type=float, default=4.0)
    a = ap.parse_args()
    paths = [p for p in sorted(sum((glob.glob(f) for f in a.frames), []))
             if sh.is_daylight(p, a.min_lux)]
    if len(paths) < 4:
        sys.exit("need >=4 daylight frames")
    ref = a.ref or paths[0]                         # morning reference

    times, units, series = gray_series(paths, ref)
    M = np.array([series[u] for u in units], float)
    common = np.nanmedian(M, axis=0)                # shared lighting per frame
    resid = {u: list(np.array(series[u], float) - common) for u in units}

    rows = []
    for u in units:
        c = he.classify_series(resid[u], a.k_sigma)
        rows.append((u, c, resid[u]))
    rows.sort(key=lambda r: -r[1]["score"])

    hh = " ".join(f"{t:>4d}" for t in times)
    print(f"frames (local h): {hh}   ref={os.path.basename(ref)[11:13]}:00Z, raw-gray structural diff\n")
    print(f"{'unit':>16} {'verdict':>7} {'score':>5} {'step':>5}   series")
    for u, c, s in rows:
        if c["kind"] == "none":
            continue
        # a persistent step in the STRUCTURAL feature = a move (vs harvest's reflectance step)
        verdict = "MOVE" if c["kind"] == "harvest" else c["kind"]
        nm = F.NAMES.get(u, str(u))
        step = f"{times[c['step_at']]:>2d}h" if c["step_at"] is not None else "-"
        spark = " ".join(f"{v:4.0f}" if v == v else "  - " for v in s)
        mk = "  <== chilli (known move)" if u in CHILLI_UNITS else ""
        print(f"{nm:>16} {verdict:>7} {c['score']:5.1f} {step:>5}   {spark}{mk}")
    moves = [F.NAMES.get(u) for u, c, _ in rows if c["kind"] == "harvest"]
    print("\nflagged moves:", ", ".join(moves) if moves else "(none)")


if __name__ == "__main__":
    main()
