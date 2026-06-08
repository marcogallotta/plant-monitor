#!/usr/bin/env python3
"""Core stabilization-transform computation, factored out of compute_stabilization
so it can be unit-tested without a database (see scripts/test_stabilization.py).

Given an ordered list of frame paths + a reference filename, returns one record
per frame describing how to warp it onto the reference. The pipeline:

  1. classify NIGHT frames by mean luminance and drop them (near-black frames
     break feature matching across the overnight gap);
  2. chain daytime frames outward from the reference, WIDENing past a weak hop;
  3. QUALITY-GATE each kept frame by re-checking its alignment to the reference,
     dropping any that still land far off (a chain that crossed a weak cross-night
     hop can mis-scale a whole cluster -> a big jump at the boundary).

Dropped frames (night / failed / low_quality) get matrix=None.
"""
import numpy as np
import cv2

import scripts.frame_registration as fr

WORK_WIDTH = 1600          # registration resolution; matrix is in these px
NIGHT_LUMA = 40            # mean 8-bit luminance below this = a night shot
WIDEN = 3                  # daytime neighbours to try when a hop fails
RESID_GATE_FRAC = 0.02     # drop a frame still misaligned by >this fraction of width


def mean_luma(bgr, width=320):
    """Mean brightness on a downscaled frame. Night ≈3-18, daytime ≈100-125."""
    h = int(round(bgr.shape[0] * width / bgr.shape[1]))
    g = cv2.cvtColor(cv2.resize(bgr, (width, h), interpolation=cv2.INTER_AREA),
                     cv2.COLOR_BGR2GRAY)
    return float(g.mean())


def corner_disp(M, w, h):
    """Max displacement (px) of the four frame corners under a 2x3 transform."""
    pts = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    wp = cv2.transform(pts, M).reshape(-1, 2)
    return float(np.max(np.linalg.norm(wp - pts.reshape(-1, 2), axis=1)))


def residual_to_ref(ref_gray, frame_gray, M, w, h):
    """How far a warped frame still misaligns to the reference (px). A correct M
    lands it on the reference (≈0); a chain that drifted lands it far off."""
    warped = cv2.warpAffine(frame_gray, M, (w, h))
    Mres, hi, gi = fr.register_pair(ref_gray, warped)
    return corner_disp(Mres, w, h) if Mres is not None else float("inf")


def compute_transforms(paths, reference_name, work_width=WORK_WIDTH,
                       night_luma=NIGHT_LUMA, widen=WIDEN,
                       resid_gate_frac=RESID_GATE_FRAC):
    """paths: frame paths already ordered by capture time. reference_name: the
    anchor frame's basename (must appear in paths and read as daytime).

    Returns a list of records aligned to `paths`, each:
        {"path", "luma", "status", "matrix" (2x3 np.float32 | None),
         "ref_w", "ref_h"}
    status ∈ {anchor, registered, night, failed, low_quality}.
    """
    n = len(paths)
    grays, dims, luma = [None] * n, [None] * n, [None] * n
    for i, p in enumerate(paths):
        bgr = cv2.imread(str(p))
        if bgr is None:
            luma[i] = None
            continue
        luma[i] = mean_luma(bgr)
        w = min(work_width, bgr.shape[1])
        h = int(round(bgr.shape[0] * w / bgr.shape[1]))
        grays[i] = fr.features_gray(cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA))
        dims[i] = (w, h)

    is_day = [lu is not None and lu >= night_luma for lu in luma]
    day = [i for i, d in enumerate(is_day) if d]
    anchor = next((i for i, p in enumerate(paths)
                   if str(p).endswith(reference_name)), None)
    if anchor is None or not is_day[anchor]:
        raise ValueError(f"reference {reference_name!r} missing or not daytime")

    ref_w, ref_h = dims[anchor]
    M = [None] * n
    status = ["night" if not is_day[i] else None for i in range(n)]
    M[anchor], status[anchor] = np.float32([[1, 0, 0], [0, 1, 0]]), "anchor"
    a = day.index(anchor)

    def anchor_frame(i, cand_positions):
        for pos in cand_positions:
            j = day[pos]
            if M[j] is None:
                continue
            Mi, hi, gi = fr.register_pair(grays[j], grays[i])  # i -> j
            if fr.plausible(Mi, hi, gi):
                return fr.compose(M[j], Mi)
        return None

    for p in range(a + 1, len(day)):       # forward in time
        Mi = anchor_frame(day[p], [p - k for k in range(1, widen + 1) if p - k >= a])
        M[day[p]], status[day[p]] = (Mi, "registered") if Mi is not None else (None, "failed")
    for p in range(a - 1, -1, -1):         # backward in time
        Mi = anchor_frame(day[p], [p + k for k in range(1, widen + 1) if p + k < len(day)])
        M[day[p]], status[day[p]] = (Mi, "registered") if Mi is not None else (None, "failed")

    # Quality gate: drop frames that still land far off the reference.
    gate_px = resid_gate_frac * ref_w
    for i in day:
        if M[i] is None or i == anchor:
            continue
        if residual_to_ref(grays[anchor], grays[i], M[i], ref_w, ref_h) > gate_px:
            M[i], status[i] = None, "low_quality"

    return [{"path": paths[i], "luma": luma[i], "status": status[i],
             "matrix": M[i], "ref_w": ref_w, "ref_h": ref_h} for i in range(n)]
