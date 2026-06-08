#!/usr/bin/env python3
"""Landmark-based registration for the Pi overhead camera + region diff/inherit.

The mount is a wind-nudged temporary rig, so frames drift slowly (a few px and
a fraction of a degree per hour). To carry the human-verified region tags on the
canonical reference frame forward to later frames, a new frame must first be
aligned onto the reference. This module does that robustly and then supports the
two things Phase-2 diff/inherit needs:

  * register_to_reference() — align an arbitrary frame onto the reference.
  * warp_region()          — project a normalised region tag through a transform
                             (forward: target->ref for diffing; inverse:
                             ref->target to INHERIT the tag onto a new frame).
  * region_change()        — per-region mean-abs-diff after alignment; low =
                             unchanged (inherit identity for free), high =
                             something moved here (re-confirm).

Robustness recipe (established empirically, see the experiment that produced it):

  1. CLAHE light-normalise before ORB. Local contrast equalisation makes feature
     matching survive the shadow movement that otherwise wrecks it.
  2. Gate on POST-registration confidence (inlier count + ratio + a plausible
     rigid transform), NOT on a pre-check. Global brightness/histogram compares
     are false predictors here — the problem is local shadow motion, invisible
     to a global metric.
  3. Chain through intermediate hourly frames when a direct attempt is weak.
     A 3-4h lighting gap breaks ORB; one-hour hops never do, and the small
     rigid transforms compose cleanly. This rescues every pair that direct
     registration fails on.

Usage:
    .venv/bin/python scripts/frame_registration.py TARGET [REFERENCE]
    # defaults: TARGET=2026-06-07T070020Z.jpg  REFERENCE=2026-06-07T130010Z.jpg
Registers TARGET onto REFERENCE (direct, falling back to chained), then reports
per-region change for the tags in scripts/reference_regions.json.
"""
import sys
import os
import re
import json
import math
import glob
import numpy as np
import cv2

PHOTOS_DIR = "data/photos"
REFERENCE_FRAME = "2026-06-07T130010Z.jpg"
REGIONS_FILE = os.path.join(os.path.dirname(__file__), "reference_regions.json")

# Confidence thresholds for trusting a single registration hop.
MIN_INLIERS = 20
MIN_INLIER_RATIO = 0.30
MAX_ROTATION_DEG = 10.0
MAX_TRANSLATION_PX = 200

_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{6}Z)")


# --- image helpers ---------------------------------------------------------

def load_bgr(path):
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"could not read {path}")
    return img


def features_gray(bgr):
    """CLAHE-normalised grayscale — the input ORB actually matches on."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)


# --- core registration -----------------------------------------------------

def register_pair(ref_g, tgt_g, ransac_thresh=5.0):
    """Estimate a rigid (rot+trans+uniform-scale) transform mapping tgt->ref.

    Returns (M 2x3 or None, inliers, good_matches). Partial-affine, not full
    projective: the drift is rigid, and constraining the model is far more
    robust with few inliers (no degenerate stretching).
    """
    orb = cv2.ORB_create(nfeatures=8000)
    k1, d1 = orb.detectAndCompute(ref_g, None)
    k2, d2 = orb.detectAndCompute(tgt_g, None)
    if d1 is None or d2 is None:
        return None, 0, 0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    raw = bf.knnMatch(d2, d1, k=2)
    # knnMatch(k=2) can return pairs with <2 neighbours; skip those before the
    # Lowe ratio test rather than blindly unpacking (m, n).
    good = [pair[0] for pair in raw
            if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance]
    if len(good) < 12:
        return None, 0, len(good)
    src = np.float32([k2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                          ransacReprojThreshold=ransac_thresh)
    if M is None:
        return None, 0, len(good)
    return M, int(mask.sum()), len(good)


def decompose(M):
    """(rotation_deg, scale, tx, ty) of a 2x3 partial-affine transform."""
    a, b = M[0, 0], M[1, 0]
    return (math.degrees(math.atan2(b, a)), math.hypot(a, b),
            float(M[0, 2]), float(M[1, 2]))


def plausible(M, inliers, good):
    """Is this a believable fixed-mount drift transform?"""
    if M is None or good == 0:
        return False
    rot, scale, tx, ty = decompose(M)
    return (inliers >= MIN_INLIERS and inliers / good >= MIN_INLIER_RATIO and
            abs(rot) < MAX_ROTATION_DEG and 0.9 < scale < 1.1 and
            abs(tx) < MAX_TRANSLATION_PX and abs(ty) < MAX_TRANSLATION_PX)


def compose(M_outer, M_inner):
    """Compose two 2x3 affines: result applies M_inner then M_outer.

    For chaining transforms A->B and B->C into A->C, the inner runs first:
        compose(B_to_C, A_to_B) == A_to_C
    """
    A = np.vstack([M_inner, [0, 0, 1]])
    B = np.vstack([M_outer, [0, 0, 1]])
    return (B @ A)[:2].astype(np.float32)


def invert(M):
    """Invert a 2x3 affine transform."""
    return cv2.invertAffineTransform(M)


# --- chaining --------------------------------------------------------------

def _timestamp(path):
    m = _TS_RE.search(os.path.basename(path))
    return m.group(1) if m else None


def discover_chain(target_path, reference_path, photos_dir=PHOTOS_DIR):
    """Ordered frames from the target toward the reference (exclusive of target,
    inclusive of reference), so consecutive pairs are small temporal hops."""
    t_ts, r_ts = _timestamp(target_path), _timestamp(reference_path)
    if not t_ts or not r_ts:
        raise ValueError(
            f"cannot parse YYYY-MM-DDTHHMMSSZ timestamp from "
            f"{os.path.basename(target_path)!r} / {os.path.basename(reference_path)!r}")
    frames = []
    for p in glob.glob(os.path.join(photos_dir, "*.jpg")):
        ts = _timestamp(p)
        if ts and min(t_ts, r_ts) <= ts <= max(t_ts, r_ts):
            frames.append((ts, p))
    frames.sort(key=lambda x: x[0], reverse=(t_ts > r_ts))
    return [p for ts, p in frames if ts != t_ts]


def register_to_reference(target_path, reference_path=None, photos_dir=None):
    """Align target onto reference by chaining through intermediate hourly frames.

    A direct big-time-gap registration is unreliable (shadow movement breaks
    feature matching, and a high inlier count does NOT guarantee the best fit —
    verified: a 303-inlier direct fit aligned static structure worse than the
    chain). Small one-hour hops never break and their rigid transforms compose
    cleanly, so we always walk the chain. The degenerate case (no intermediate
    frame between target and reference) is a single hop == a direct attempt.

    If a hop is weak, it is skipped and the chain bridges to the next frame
    (a wider but still attempted hop) — retry rather than give up. Returns:

        {"M": 2x3|None, "method": "chained"|"direct"|"failed",
         "inliers": int, "good": int, "hops": [...], "reason": str|None}
    """
    # Chain frames are siblings of the target; derive the dir from it so a
    # target outside PHOTOS_DIR (e.g. test fixtures) doesn't pull full-res
    # intermediates from PHOTOS_DIR and scale-mismatch.
    if photos_dir is None:
        photos_dir = os.path.dirname(target_path) or PHOTOS_DIR
    if reference_path is None:
        reference_path = os.path.join(photos_dir, REFERENCE_FRAME)
    chain = discover_chain(target_path, reference_path, photos_dir)
    if not chain:
        return {"M": None, "method": "failed", "inliers": 0, "good": 0,
                "hops": [], "reason": "no path frames found (incl. reference)"}

    path_frames = [target_path] + chain  # last entry is the reference
    grays = {}

    def gray(p):
        if p not in grays:
            grays[p] = features_gray(load_bgr(p))
        return grays[p]

    M_acc = None
    hops = []
    src_idx = 0
    while src_idx < len(path_frames) - 1:
        # Try the nearest next frame; on a weak hop, skip it and bridge further.
        dst_idx = src_idx + 1
        landed = False
        while dst_idx < len(path_frames):
            a, b = path_frames[src_idx], path_frames[dst_idx]
            Mi, hi, gi = register_pair(gray(b), gray(a))  # a -> b
            ok = plausible(Mi, hi, gi)
            hops.append({"from": _timestamp(a), "to": _timestamp(b),
                         "inliers": hi, "good": gi, "ok": ok,
                         "skipped": dst_idx - src_idx - 1})
            if ok:
                M_acc = Mi if M_acc is None else compose(Mi, M_acc)
                src_idx = dst_idx
                landed = True
                break
            dst_idx += 1  # skip the weak intermediate, try a wider hop
        if not landed:
            return {"M": None, "method": "failed",
                    "inliers": hops[-1]["inliers"], "good": hops[-1]["good"],
                    "hops": hops,
                    "reason": f"no reliable hop from {_timestamp(path_frames[src_idx])}"}

    method = "direct" if len(hops) == 1 else "chained"
    return {"M": M_acc, "method": method, "inliers": hops[-1]["inliers"],
            "good": hops[-1]["good"], "hops": hops, "reason": None}


# --- regions ---------------------------------------------------------------

def norm_corners(region):
    """min/max-normalise a region dict to (x0,y0,x1,y1) with x0<=x1, y0<=y1."""
    x0, x1 = sorted((region["x"], region["x2"]))
    y0, y1 = sorted((region["y"], region["y2"]))
    return x0, y0, x1, y1


def warp_region(M, region, w, h):
    """Project a normalised region through transform M (which maps pixels in the
    region's own frame to the destination frame). Returns the axis-aligned
    normalised bbox enclosing the four warped corners.

    Forward (M = target->ref): map a target-frame region into reference space.
    Inherit (M = invert(ref->target)): map a reference tag onto a new frame.
    """
    x0, y0, x1, y1 = norm_corners(region)
    pts = np.float32([[x0 * w, y0 * h], [x1 * w, y0 * h],
                      [x1 * w, y1 * h], [x0 * w, y1 * h]]).reshape(-1, 1, 2)
    wp = cv2.transform(pts, M).reshape(-1, 2)
    return (float(wp[:, 0].min() / w), float(wp[:, 1].min() / h),
            float(wp[:, 0].max() / w), float(wp[:, 1].max() / h))


def region_change(ref_bgr, warped_tgt_bgr, region):
    """Mean abs grayscale diff inside a reference-space region. Both images must
    already be in reference space (warp the target first).

    Raw grayscale on purpose: CLAHE is right for feature matching but amplifies
    shadow texture and makes this metric WORSE (verified). The metric is still
    lighting-sensitive, so it is only meaningful between frames close in TIME
    (same sun position). Geometric inheritance can chain to the canonical
    reference; photometric change-detection should diff against the nearest-in-
    time known-good frame instead.
    """
    h, w = ref_bgr.shape[:2]
    x0, y0, x1, y1 = norm_corners(region)
    cx0, cx1 = int(round(x0 * w)), int(round(x1 * w))
    cy0, cy1 = int(round(y0 * h)), int(round(y1 * h))
    cx0, cx1 = max(0, min(cx0, cx1)), min(w, max(cx0, cx1))
    cy0, cy1 = max(0, min(cy0, cy1)), min(h, max(cy0, cy1))
    if cx1 <= cx0 or cy1 <= cy0:
        # Region warped off-frame / degenerate. NaN, not 0.0, so an absent
        # region can't masquerade as "no change".
        return float("nan")
    a = cv2.cvtColor(ref_bgr[cy0:cy1, cx0:cx1], cv2.COLOR_BGR2GRAY).astype(np.float32)
    b = cv2.cvtColor(warped_tgt_bgr[cy0:cy1, cx0:cx1], cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float(np.abs(a - b).mean())


def load_regions(path=REGIONS_FILE):
    """Plant region tags as a flat list of dicts. NOTE: unit_id is NOT unique — a
    unit can span several regions (e.g. unit 16 has three boxes). Group by unit_id
    if you need per-unit aggregates."""
    with open(path) as f:
        return json.load(f)["regions"]


def load_controls(path=REGIONS_FILE):
    """Fixed NON-plant reference patches (wall, road, railing, sign, glass...).
    Each is {label, x, y, x2, y2}. These are negative controls: the per-frame
    component shared across them estimates global reference error (roof/exposure
    leakage) WITHOUT touching the plant cohort, so a real broad sun-sweep across
    plants is not erased. Returns [] for an older fixture with no controls."""
    with open(path) as f:
        return json.load(f).get("controls", [])


# --- CLI demo --------------------------------------------------------------

def _demo(target_path, reference_path):
    print(f"TARGET    = {target_path}")
    print(f"REFERENCE = {reference_path}\n")
    res = register_to_reference(target_path, reference_path)
    if res["hops"]:
        print("chain hops (target -> reference):")
        for hp in res["hops"]:
            flag = "ok " if hp["ok"] else "BAD"
            print(f"  [{flag}] {hp['from']} -> {hp['to']}  "
                  f"inliers={hp['inliers']}/{hp['good']}")
    if res["M"] is None:
        print(f"\nREGISTRATION FAILED ({res['method']}): {res['reason']}")
        return 1
    rot, scale, tx, ty = decompose(res["M"])
    print(f"\nmethod={res['method']}  inliers={res['inliers']}/{res['good']}")
    print(f"transform: rot={rot:+.2f} deg  scale={scale:.3f}  "
          f"translation=({tx:+.0f},{ty:+.0f}) px")

    ref_bgr = load_bgr(reference_path)
    tgt_bgr = load_bgr(target_path)
    h, w = ref_bgr.shape[:2]
    warped = cv2.warpAffine(tgt_bgr, res["M"], (w, h))

    regions = load_regions()
    print(f"\nper-region mean-abs-diff for {len(regions)} tags "
          f"(before vs after alignment):")
    rows = []
    for r in regions:
        before = region_change(ref_bgr, tgt_bgr, r)
        after = region_change(ref_bgr, warped, r)
        rows.append((r["unit_id"], before, after))
    for unit_id, before, after in sorted(rows, key=lambda x: -(x[2] if x[2] == x[2] else -1)):
        if after != after:  # NaN: region warped off-frame
            print(f"  unit {unit_id:>3}: off-frame after alignment")
            continue
        delta = (before - after) / before * 100 if before else 0
        print(f"  unit {unit_id:>3}: before={before:5.1f}  after={after:5.1f}  "
              f"({delta:+4.0f}%)")
    on = [(b, a) for _, b, a in rows if a == a and b == b]
    if on:
        mean_before = sum(b for b, _ in on) / len(on)
        mean_after = sum(a for _, a in on) / len(on)
        print(f"\nmean across {len(on)} on-frame regions: "
              f"before={mean_before:.1f}  after={mean_after:.1f}")
    print("NOTE: raw absdiff in plant regions is dominated by foliage sway + "
          "lighting, not\njust geometric drift — it is NOT yet a reliable "
          "change detector. Registration\n(the geometric layer) is solid; a "
          "sway/lighting-robust change signal is the next step.")
    return 0


if __name__ == "__main__":
    tgt = sys.argv[1] if len(sys.argv) > 1 else f"{PHOTOS_DIR}/2026-06-07T070020Z.jpg"
    ref = sys.argv[2] if len(sys.argv) > 2 else f"{PHOTOS_DIR}/{REFERENCE_FRAME}"
    sys.exit(_demo(tgt, ref))
