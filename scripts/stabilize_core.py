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
import os
import hashlib

import numpy as np
import cv2

import scripts.frame_registration as fr

# Statuses that are settled — the incremental worker reuses them instead of
# recomputing. (A 'pending' frame, or one with no record, is (re)computed.)
FINAL_STATUSES = {"registered", "anchor", "night", "low_quality", "failed"}

WORK_WIDTH = 1600          # registration resolution; matrix is in these px
NIGHT_LUMA = 40            # mean 8-bit luminance below this = a night shot
WIDEN = 3                  # daytime neighbours to try when a hop fails
RESID_GATE_FRAC = 0.04     # drop a frame still misaligned by >this fraction of width
                           # (was 0.02; raised because 2-day chain drift lands at ~2-4%
                           # while cross-night cluster mis-registrations land at 7%+,
                           # so 4% is the safe midpoint between the two populations)

# Bump on algorithm changes that DON'T alter the tunables below (e.g. a change to
# the registration/gate logic). Combined with the tunables + reference into the
# per-frame fingerprint so stale matrices auto-invalidate on any material change.
ALGO_REV = 3


def fingerprint(reference_name, work_width=WORK_WIDTH, night_luma=NIGHT_LUMA,
                widen=WIDEN, resid_gate_frac=RESID_GATE_FRAC):
    """Short hash identifying the algorithm + params + reference a transform was
    produced with. A frame whose stored fingerprint differs is recomputed."""
    payload = f"{ALGO_REV}|{reference_name}|{work_width}|{night_luma}|{widen}|{resid_gate_frac}"
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


def needs_recompute(prior_entry, version):
    """True if a frame must be (re)computed: no prior, not settled, or produced
    by a different algorithm/param fingerprint."""
    if not prior_entry or prior_entry.get("status") not in FINAL_STATUSES:
        return True
    return prior_entry.get("version") != version


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
                       resid_gate_frac=RESID_GATE_FRAC, prior=None):
    """paths: frame paths already ordered by capture time. reference_name: the
    anchor frame's basename (must appear in paths and read as daytime).

    `prior` (optional) maps a frame basename -> {"status", "matrix" (6 floats|None)}
    of an earlier run. Frames whose prior status is settled (FINAL_STATUSES) are
    reused as-is; only frames that are new or 'pending' are (re)computed. With no
    prior this does a full compute. Images are loaded lazily, so an incremental
    run only decodes the new frame + its neighbour + the reference.

    Returns a list of records aligned to `paths`, each:
        {"path", "luma", "status", "matrix" (2x3 np.float32 | None),
         "ref_w", "ref_h"}
    status ∈ {anchor, registered, night, failed, low_quality}.
    """
    prior = prior or {}
    version = fingerprint(reference_name, work_width, night_luma, widen, resid_gate_frac)
    n = len(paths)
    names = [os.path.basename(str(p)) for p in paths]
    _cache = {}

    def _load(i):
        if i not in _cache:
            bgr = cv2.imread(str(paths[i]))
            if bgr is None:
                _cache[i] = (None, None, None)
            else:
                w = min(work_width, bgr.shape[1])
                h = int(round(bgr.shape[0] * w / bgr.shape[1]))
                g = fr.features_gray(cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA))
                _cache[i] = (g, (w, h), mean_luma(bgr))
        return _cache[i]

    def gray(i): return _load(i)[0]
    def dims(i): return _load(i)[1]
    def luma(i): return _load(i)[2]

    anchor = next((i for i in range(n) if names[i] == reference_name), None)
    if anchor is None:
        raise ValueError(f"reference {reference_name!r} not in paths")

    M = [None] * n
    status = [None] * n
    is_day = [False] * n
    computed = [False] * n   # (re)computed this run -> needs the quality gate

    # Reuse settled frames from a prior run (no image decode needed) — but only
    # if they were produced by the current algorithm/param fingerprint.
    for i in range(n):
        pr = prior.get(names[i])
        if needs_recompute(pr, version):
            continue                       # new / pending / stale -> compute below
        status[i] = pr["status"]
        if pr["status"] in ("registered", "anchor") and pr.get("matrix"):
            M[i] = np.float32(pr["matrix"]).reshape(2, 3)
            is_day[i] = True               # candidate to chain new frames onto

    # The reference is always the daytime identity anchor.
    if dims(anchor) is None:
        raise ValueError("reference image unreadable")
    ref_w, ref_h = dims(anchor)
    M[anchor], status[anchor], is_day[anchor] = np.float32([[1, 0, 0], [0, 1, 0]]), "anchor", True

    # Classify the frames that still need computing.
    for i in range(n):
        if status[i] is not None:
            continue
        lu = luma(i)
        if lu is None:
            status[i] = "failed"
        elif lu < night_luma:
            status[i] = "night"
        else:
            is_day[i] = True               # daytime, M still None -> register below

    day = [i for i in range(n) if is_day[i]]
    a = day.index(anchor)

    gate_px = resid_gate_frac * ref_w

    def anchor_frame(i, cand_positions):
        for pos in cand_positions:
            j = day[pos]
            if M[j] is None:
                continue
            Mi, hi, gi = fr.register_pair(gray(j), gray(i))  # i -> j
            if not fr.plausible(Mi, hi, gi):
                continue
            composed = fr.compose(M[j], Mi)
            if residual_to_ref(gray(anchor), gray(i), composed, ref_w, ref_h) <= gate_px:
                return composed
        return None

    def register(p, cand_positions):       # only frames without a matrix yet
        i = day[p]
        if M[i] is not None:
            return
        Mi = anchor_frame(i, cand_positions)
        if Mi is not None:
            M[i], status[i], computed[i] = Mi, "registered", True
        else:
            status[i] = "failed"

    for p in range(a + 1, len(day)):       # forward in time
        register(p, [p - k for k in range(1, widen + 1) if p - k >= a])
    for p in range(a - 1, -1, -1):         # backward in time
        register(p, [p + k for k in range(1, widen + 1) if p + k < len(day)])

    return [{"path": paths[i], "luma": _cache.get(i, (None, None, None))[2],
             "status": status[i], "matrix": M[i], "version": version,
             "ref_w": ref_w, "ref_h": ref_h} for i in range(n)]
