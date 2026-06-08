#!/usr/bin/env python3
"""Per-region MOVE detector — spot when a pot is relocated (no manual logging).

ANY pot can move and the user won't log it, so the camera must detect it — the
generic form of the chilli sun-chase, and the design's own diff/inherit principle.

Feature search (all validated on the known 2026-06-08 chilli move — 3 pots+seedlings
at 10:00 local, gone by ~16:00, abrupt at ~17:00):
  * Finlayson reflectance invariant (harvest/wilt's feature) — BLIND (terracotta-pot
    vs tile have similar chromaticity).
  * raw-gray structural diff — responds but lighting-noisy.
  * (eps-)census / structure — BLIND here: the pots are flat dark soil + tiny
    seedlings and bare tile is also low-texture, so the move barely changes texture.
  * mean COLOUR vs a fixed morning frame — catches it, but slow lighting/growth
    colour DRIFT gives big false positives (e.g. Rocket).
  * WINNER — mean colour, CONSECUTIVE-FRAME (short baseline): a move is an ABRUPT
    colour jump; comparing frame-to-frame cancels slow drift (Rocket falls away)
    and pinpoints the move hour. This is the "removed-object" abrupt-change paradigm.

So: per region, per frame, mean CIELAB; distance to the PREVIOUS frame; common-mode
(per-frame median) removed to cancel global lighting jolts. A move = a jump above
threshold. Each frame is chained-registered to the reference first.

STATUS — PROTOTYPE, not a clean detector yet. It surfaces the chilli move (the 3
pots spike at ~17:00), but two unsolved confounds remain on this one marginal day:
  (1) REGISTRATION WOBBLE at the frame edge — the bottom (where the chillis sit)
      misaligns at 10:00 (direct reg there is "not plausible"; chained still wobbles),
      producing a false colour spike that rivals the real move, so argmax can pick
      the wrong hour. Needs robust edge registration before this is trustworthy.
  (2) Only ~1 post-move frame today (move landed at the end of the arc), so the
      persistence confirmation that separates a move from a one-off jolt can't run.
Remaining work: robust edge registration; multi-cue confirmation (colour jump +
the region's new state holding); validate on a move with several post-move frames
(and ideally several real moves). The FEATURE knowledge above is the durable result.

    .venv/bin/python scripts/move_detect.py 'data/photos/2026-06-08T*Z.jpg'
"""
import os, sys, glob, argparse
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.frame_registration as fr
import scripts.finlayson_experiment as F
import scripts.sun_hours as sh

CHILLI_UNITS = {34, 35, 36}            # known 2026-06-08 move — validation handle


def region_lab(path, ref, ref_path, w, h, regs):
    """Per-region mean CIELAB of a frame (chained-registered to the reference)."""
    im = cv2.imread(path)
    if os.path.abspath(path) != os.path.abspath(ref_path):
        res = fr.register_to_reference(path, ref_path)        # chained hops
        if res["M"] is not None:
            im = cv2.warpAffine(im, res["M"], (w, h))
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
    out = {}
    for u, rs in regs.items():
        ms = [F._crop(lab, r).reshape(-1, 3).mean(0) for r in rs if F._crop(lab, r) is not None]
        out[u] = np.mean(ms, 0) if ms else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", nargs="+")
    ap.add_argument("--ref", help="registration reference (default: first daylight frame)")
    ap.add_argument("--min-lux", type=float, default=50.0)
    ap.add_argument("--thr", type=float, default=40.0, help="abrupt mean-LAB jump = a move")
    a = ap.parse_args()
    paths = [p for p in sorted(sum((glob.glob(f) for f in a.frames), []))
             if sh.is_daylight(p, a.min_lux)]
    if len(paths) < 3:
        sys.exit("need >=3 daylight frames")
    ref_path = a.ref or paths[0]
    ref = cv2.imread(ref_path); h, w = ref.shape[:2]
    regs = {}
    for r in fr.load_regions():
        regs.setdefault(r["unit_id"], []).append(r)

    times, prev, jump = [], None, {u: [] for u in regs}
    for p in paths:
        lab = region_lab(p, ref, ref_path, w, h, regs)
        times.append((sh.frame_time(p).hour + sh.UTC_OFFSET_H) % 24)
        for u in regs:
            if prev is None or prev[u] is None or lab[u] is None:
                jump[u].append(0.0)
            else:
                jump[u].append(float(np.linalg.norm(lab[u] - prev[u])))
        prev = lab

    # COMMON-MODE removal: a global lighting shift or a registration wobble jolts
    # EVERY region together (the morning sunrise/10h artifacts), so subtract the
    # per-frame median jump across regions. A real move is region-specific and
    # survives; the shared artifact cancels.
    U = sorted(regs)
    J = np.array([jump[u] for u in U], float)
    common = np.median(J, axis=0)
    jump = {u: list(J[i] - common) for i, u in enumerate(U)}

    moved = {u: (int(np.argmax(jump[u])) if max(jump[u]) > a.thr else None) for u in regs}
    units = sorted(regs, key=lambda u: -max(jump[u]))
    print(f"frames (local h): {' '.join(f'{t:>3d}' for t in times)}   "
          f"ref={os.path.basename(ref_path)[11:13]}:00Z, abrupt mean-LAB jump\n")
    print(f"{'unit':>16} {'move':>5} {'at':>4}   jump series")
    for u in units:
        i = moved[u]
        at = f"{times[i]:>2d}h" if i is not None else "-"
        spark = " ".join(f"{v:3.0f}" for v in jump[u])
        mk = "  <== chilli" if u in CHILLI_UNITS else ""
        if max(jump[u]) > a.thr * 0.6:
            print(f"{F.NAMES.get(u, str(u)):>16} {('YES' if i is not None else ''):>5} {at:>4}   {spark}{mk}")
    flagged = [F.NAMES.get(u) for u in units if moved[u] is not None]
    print("\nflagged moves:", ", ".join(flagged) if flagged else "(none)")


if __name__ == "__main__":
    main()
