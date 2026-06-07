#!/usr/bin/env python3
"""Standalone experiment: a LIGHTING-ROBUST region-change signal.

Geometric alignment (frame_registration) is solid and sway is handled at capture
(burst->plate). The remaining confound is LIGHTING: raw grayscale absdiff in a
region is dominated by sun/shadow motion, so it cannot tell "a shadow crossed the
rocket" from "the rocket was harvested". This A/Bs candidate metrics that ignore
illumination while keeping real structural change.

Ground truth: a known -20g DILL harvest (unit 4) between the 2026-06-06 17:00Z and
18:00Z overhead frames. A good metric ranks unit 4 at/near the TOP while raw
absdiff buries it among lighting-only regions.

Metrics (all "distance": higher = more changed):
  raw   - mean abs gray diff (the current region_change; lighting-sensitive)
  zncc  - 1 - zero-normalised cross-correlation. Cancels per-region affine
          brightness/contrast (a uniform lighting shift), but not a shadow moving
          WITHIN the region.
  grad  - 1 - NCC of Sobel gradient MAGNITUDE. Lighting changes intensity
          smoothly; harvest changes edges/texture. Robust to brightness AND to a
          shadow edge that merely translates intensity.

Usage:
    .venv/bin/python scripts/lighting_experiment.py [REF_FRAME TGT_FRAME]
    # defaults to the dill-harvest pair 2026-06-06T170006Z -> T180004Z
"""
import os
import sys
import numpy as np
import cv2

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import scripts.frame_registration as fr

PHOTOS = os.path.join(REPO, "data", "photos")
DEFAULT_REF = os.path.join(PHOTOS, "2026-06-06T170006Z.jpg")   # before harvest
DEFAULT_TGT = os.path.join(PHOTOS, "2026-06-06T180004Z.jpg")   # after  harvest
DILL_UNIT = 4


def _crop(bgr, region):
    h, w = bgr.shape[:2]
    x0, y0, x1, y1 = fr.norm_corners(region)
    cx0, cx1 = sorted((int(round(x0 * w)), int(round(x1 * w))))
    cy0, cy1 = sorted((int(round(y0 * h)), int(round(y1 * h))))
    cx0, cy0 = max(0, cx0), max(0, cy0)
    cx1, cy1 = min(w, cx1), min(h, cy1)
    if cx1 - cx0 < 3 or cy1 - cy0 < 3:
        return None
    return cv2.cvtColor(bgr[cy0:cy1, cx0:cx1], cv2.COLOR_BGR2GRAY).astype(np.float32)


def _ncc(a, b):
    """Zero-normalised cross-correlation of two equal-size float patches, [-1,1]."""
    a = a - a.mean(); b = b - b.mean()
    da, db = np.sqrt((a * a).sum()), np.sqrt((b * b).sum())
    if da < 1e-6 or db < 1e-6:
        return 1.0  # flat patch: treat as identical (no structure to differ)
    return float((a * b).sum() / (da * db))


def _gradmag(p):
    gx = cv2.Sobel(p, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(p, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gx, gy)


def metrics(ref_bgr, tgt_bgr, region):
    a, b = _crop(ref_bgr, region), _crop(tgt_bgr, region)
    if a is None or b is None or a.shape != b.shape:
        return None
    raw = float(np.abs(a - b).mean())
    zncc = 1.0 - _ncc(a, b)
    grad = 1.0 - _ncc(_gradmag(a), _gradmag(b))
    return raw, zncc, grad


def _rank_of(rows, idx, unit):
    """1-based rank of `unit` when rows are sorted desc by column idx."""
    order = sorted(rows, key=lambda r: -r[1][idx])
    for i, r in enumerate(order, 1):
        if r[0] == unit:
            return i
    return None


def main():
    ref_p = sys.argv[1] if len(sys.argv) > 2 else DEFAULT_REF
    tgt_p = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_TGT
    ref = fr.load_bgr(ref_p)
    tgt = fr.load_bgr(tgt_p)

    # Align target onto ref (these are 1h apart -> a single robust hop).
    res = fr.register_pair(fr.features_gray(ref), fr.features_gray(tgt))
    M = res[0]
    if M is not None and fr.plausible(*res):
        h, w = ref.shape[:2]
        tgt = cv2.warpAffine(tgt, M, (w, h))
        print(f"aligned (inliers={res[1]}/{res[2]})")
    else:
        print("WARNING: registration weak; diffing unaligned")

    regions = fr.load_regions()
    rows = []  # (unit_id, (raw, zncc, grad))
    for r in regions:
        m = metrics(ref, tgt, r)
        if m is not None:
            rows.append((r["unit_id"], m))

    print(f"\nREF={os.path.basename(ref_p)}  TGT={os.path.basename(tgt_p)}  "
          f"(dill=unit {DILL_UNIT}, known -20g harvest)\n")
    print(f"{'unit':>5}  {'raw':>7}  {'zncc':>7}  {'grad':>7}")
    for uid, (raw, zncc, grad) in sorted(rows, key=lambda r: -r[1][2]):
        mark = "  <== DILL (real harvest)" if uid == DILL_UNIT else ""
        print(f"{uid:>5}  {raw:7.1f}  {zncc:7.3f}  {grad:7.3f}{mark}")

    n = len(rows)
    print(f"\nDill (unit {DILL_UNIT}) rank out of {n} regions (1 = most-changed):")
    for idx, name in ((0, "raw "), (1, "zncc"), (2, "grad")):
        print(f"  {name}: #{_rank_of(rows, idx, DILL_UNIT)}")
    print("\nLower rank for grad/zncc than raw => lighting normalisation surfaces "
          "the real harvest\nthat raw absdiff buries under lighting noise.")


if __name__ == "__main__":
    main()
