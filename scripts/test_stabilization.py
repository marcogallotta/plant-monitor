#!/usr/bin/env python3
"""Tests for stabilize_core. Two tiers (same pattern as test_frame_registration):

  * SYNTHETIC (always run) — the gate's metrics on procedurally generated images.
  * REAL-FRAME (skip if absent) — the full pipeline on the committed downscaled Pi
    frames in testdata/frames/, asserting the behaviours we actually shipped:
    night frames excluded, the mis-aligned 06-06 cross-night cluster gated out,
    and — the regression that bit us — NO big jump between kept frames.

No pytest: cv2 isn't in the backend test image, so this runs standalone.
    .venv/bin/python scripts/test_stabilization.py
"""
import os
import sys
import glob
import math

import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.frame_registration as fr
import scripts.stabilize_core as sc

FRAMES_DIR = os.path.join(os.path.dirname(__file__), "testdata", "frames")
REFERENCE = "2026-06-07T130010Z.jpg"
NIGHT_FRAME = "2026-06-06T220017Z.jpg"
CLUSTER = ["2026-06-06T160008Z.jpg", "2026-06-06T170006Z.jpg",
           "2026-06-06T180004Z.jpg", "2026-06-06T190002Z.jpg"]


class Skip(Exception):
    """Raised by a test when its fixtures aren't available."""


def _affine(angle_deg, scale, tx, ty):
    r = math.radians(angle_deg)
    c, s = scale * math.cos(r), scale * math.sin(r)
    return np.float32([[c, -s, tx], [s, c, ty]])


def _synthetic_scene(w=640, h=480, seed=0):
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 128, np.uint8)
    for _ in range(180):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        col = tuple(int(c) for c in rng.integers(0, 256, 3))
        if rng.random() < 0.5:
            cv2.circle(img, (x, y), int(rng.integers(5, 35)), col, -1)
        else:
            d = int(rng.integers(10, 60))
            cv2.rectangle(img, (x, y), (x + d, y + d), col, -1)
    return img


def _fixtures():
    paths = sorted(glob.glob(os.path.join(FRAMES_DIR, "*.jpg")))
    have = {os.path.basename(p) for p in paths}
    if REFERENCE not in have or NIGHT_FRAME not in have:
        raise Skip("stabilization fixtures not present")
    return paths


def _by_name(recs):
    return {os.path.basename(str(r["path"])): r for r in recs}


def _max_consecutive_jump(recs):
    """Register every consecutive pair of KEPT frames after warping both to the
    reference; the residual corner displacement is the on-screen jump."""
    kept = [r for r in recs if r["matrix"] is not None]
    rw, rh = recs[0]["ref_w"], recs[0]["ref_h"]

    def warped(r):
        bgr = cv2.imread(str(r["path"]))
        w = min(sc.WORK_WIDTH, bgr.shape[1])
        h = int(round(bgr.shape[0] * w / bgr.shape[1]))
        g = fr.features_gray(cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA))
        return cv2.warpAffine(g, r["matrix"], (rw, rh))

    worst = 0.0
    for a, b in zip(kept, kept[1:]):
        M, hi, gi = fr.register_pair(warped(a), warped(b))
        if M is not None:
            worst = max(worst, sc.corner_disp(M, rw, rh))
    return worst, len(kept)


# --- synthetic: always run -------------------------------------------------

def test_corner_disp_identity_is_zero():
    assert sc.corner_disp(_affine(0, 1, 0, 0), 1000, 800) == 0.0


def test_corner_disp_pure_translation():
    # A 3-4-5 translation displaces every corner by 5px.
    assert abs(sc.corner_disp(_affine(0, 1, 3, 4), 1000, 800) - 5.0) < 1e-3


def test_mean_luma_separates_day_from_night():
    night = np.full((480, 640, 3), 6, np.uint8)
    day = np.full((480, 640, 3), 120, np.uint8)
    assert sc.mean_luma(night) < sc.NIGHT_LUMA < sc.mean_luma(day)


def test_residual_gate_flags_a_misaligned_transform():
    # A correct (identity) transform lands on the reference; a wrong one (10%
    # shrink, like the bad cross-night cluster) lands far off -> caught by the gate.
    scene = fr.features_gray(_synthetic_scene())
    h, w = scene.shape
    good = sc.residual_to_ref(scene, scene, _affine(0, 1, 0, 0), w, h)
    bad = sc.residual_to_ref(scene, scene, _affine(0, 0.9, 0, 0), w, h)
    gate = sc.RESID_GATE_FRAC * w
    assert good <= gate, good
    assert bad > gate, bad


# --- real-frame: skip if fixtures absent -----------------------------------

def test_real_reference_is_anchor():
    recs = sc.compute_transforms(_fixtures(), REFERENCE)
    assert _by_name(recs)[REFERENCE]["status"] == "anchor"


def test_real_night_frame_excluded():
    rec = _by_name(sc.compute_transforms(_fixtures(), REFERENCE))[NIGHT_FRAME]
    assert rec["status"] == "night" and rec["matrix"] is None


def test_real_cross_night_cluster_is_gated():
    # The 06-06 afternoon cluster only links to the reference through a weak
    # morning<->dusk hop that mis-scales it; the quality gate must drop it
    # (no matrix) rather than let it jump the timeline.
    by = _by_name(sc.compute_transforms(_fixtures(), REFERENCE))
    for name in CLUSTER:
        assert by[name]["matrix"] is None, (name, by[name]["status"])
        assert by[name]["status"] in ("low_quality", "failed"), by[name]["status"]


def test_real_no_big_jump_between_kept_frames():
    recs = sc.compute_transforms(_fixtures(), REFERENCE)
    worst, kept = _max_consecutive_jump(recs)
    assert kept >= 5, f"expected a usable kept sequence, got {kept}"
    # Pre-fix this boundary jumped ~120px; stabilized neighbours sit within a few px.
    assert worst < 8.0, f"max consecutive jump {worst:.1f}px is a visible snap"


def test_real_kept_frames_are_all_registered():
    recs = sc.compute_transforms(_fixtures(), REFERENCE)
    for r in recs:
        if r["matrix"] is not None:
            assert r["status"] in ("anchor", "registered"), r["status"]


def _prior_from(records, **overrides):
    prior = {}
    for r in records:
        name = os.path.basename(str(r["path"]))
        prior[name] = {
            "status": r["status"],
            "matrix": None if r["matrix"] is None else r["matrix"].reshape(-1).tolist(),
            "version": r["version"],
        }
    prior.update(overrides)
    return prior


def test_incremental_recomputes_only_pending_frames():
    paths = _fixtures()
    full = sc.compute_transforms(paths, REFERENCE)
    target = next(r for r in full if r["status"] == "registered")
    tname = os.path.basename(str(target["path"]))
    other = next(r for r in full if r["status"] == "registered"
                 and os.path.basename(str(r["path"])) != tname)
    oname = os.path.basename(str(other["path"]))

    # Mark one registered frame 'pending' (simulating a freshly-uploaded frame).
    prior = _prior_from(full, **{tname: {"status": "pending", "matrix": None}})
    inc = _by_name(sc.compute_transforms(paths, REFERENCE, prior=prior))

    # The pending frame is recomputed to the same transform...
    assert inc[tname]["status"] == "registered"
    assert np.allclose(inc[tname]["matrix"], target["matrix"], atol=1e-2)
    # ...and an untouched frame is reused exactly from prior (not re-registered).
    assert np.array_equal(inc[oname]["matrix"],
                          np.float32(prior[oname]["matrix"]).reshape(2, 3))


def test_incremental_all_pending_matches_full_compute():
    paths = _fixtures()
    full = sc.compute_transforms(paths, REFERENCE)
    prior = {os.path.basename(str(r["path"])): {"status": "pending", "matrix": None}
             for r in full}
    inc = sc.compute_transforms(paths, REFERENCE, prior=prior)
    assert [r["status"] for r in inc] == [r["status"] for r in full]


def test_stale_fingerprint_forces_recompute():
    # A settled prior with a different fingerprint (e.g. after a threshold/reference
    # change) must NOT be reused — it's recomputed with the current fingerprint.
    paths = _fixtures()
    full = sc.compute_transforms(paths, REFERENCE)
    target = next(r for r in full if r["status"] == "registered")
    tname = os.path.basename(str(target["path"]))
    prior = _prior_from(full)
    for entry in prior.values():
        entry["version"] = "stale-fp"            # simulate an older algorithm/params
    assert sc.needs_recompute(prior[tname], sc.fingerprint(REFERENCE))
    inc = _by_name(sc.compute_transforms(paths, REFERENCE, prior=prior))
    assert inc[tname]["status"] == "registered"
    assert inc[tname]["version"] == sc.fingerprint(REFERENCE)
    assert np.allclose(inc[tname]["matrix"], target["matrix"], atol=1e-2)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = skipped = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"PASS {t.__name__}")
        except Skip as e:
            skipped += 1
            print(f"SKIP {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed} passed, {skipped} skipped, {failed} failed")
    raise SystemExit(1 if failed else 0)
