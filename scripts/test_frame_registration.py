#!/usr/bin/env python3
"""Tests for frame_registration. Two tiers:

  * SYNTHETIC (always run) — algorithmic correctness on procedurally generated
    images / matrices. No data files, so they run on a clean clone / CI.
  * REAL-FRAME (skip if absent) — behaviour on the committed downscaled Pi
    frames in testdata/frames/. These exercise registration on real imagery
    (drift, lighting, foliage) that can't be synthesised.

No pytest: cv2 isn't in the backend test image, so this runs standalone.
    .venv/bin/python scripts/test_frame_registration.py
"""
import os
import math
import numpy as np
import cv2

import scripts.frame_registration as fr

FRAMES_DIR = os.path.join(os.path.dirname(__file__), "testdata", "frames")


class Skip(Exception):
    """Raised by a test when its fixtures aren't available."""


def _affine(angle_deg, scale, tx, ty):
    r = math.radians(angle_deg)
    c, s = scale * math.cos(r), scale * math.sin(r)
    return np.float32([[c, -s, tx], [s, c, ty]])


def _synthetic_scene(w=640, h=480, seed=0):
    """Deterministic high-feature image so ORB has plenty of corners to match."""
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 128, np.uint8)
    for _ in range(180):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        col = tuple(int(c) for c in rng.integers(0, 256, 3))
        if rng.random() < 0.5:
            r = int(rng.integers(5, 35))
            cv2.circle(img, (x, y), r, col, -1)
        else:
            d = int(rng.integers(10, 60))
            cv2.rectangle(img, (x, y), (x + d, y + d), col, -1)
    return img


def _fixture(stem):
    p = os.path.join(FRAMES_DIR, stem)
    if not os.path.exists(p):
        raise Skip(f"missing fixture {p}")
    return p


# --- synthetic: always run -------------------------------------------------

def test_compose_chains_transforms():
    a_to_b = _affine(2.0, 1.0, 10, -5)
    b_to_c = _affine(-1.0, 1.05, -4, 8)
    a_to_c = fr.compose(b_to_c, a_to_b)          # inner first
    pt = np.float32([[[100, 200]]])
    step = cv2.transform(cv2.transform(pt, a_to_b), b_to_c)
    assert np.allclose(cv2.transform(pt, a_to_c), step, atol=1e-3)


def test_invert_round_trips():
    M = _affine(3.0, 1.1, 20, -12)
    ident = fr.compose(fr.invert(M), M)
    assert np.allclose(ident, [[1, 0, 0], [0, 1, 0]], atol=1e-3), ident


def test_register_recovers_known_affine():
    scene = _synthetic_scene()
    h, w = scene.shape[:2]
    W = cv2.getRotationMatrix2D((w / 2, h / 2), 1.5, 1.0)
    W[0, 2] += 10; W[1, 2] += -8
    tgt = cv2.warpAffine(scene, W, (w, h))
    M, inliers, good = fr.register_pair(fr.features_gray(scene),
                                        fr.features_gray(tgt))
    assert M is not None and inliers >= 30, (inliers, good)
    assert fr.plausible(M, inliers, good)
    # M maps target->ref, so it must undo W: compose(M, W) ~ identity.
    resid = fr.compose(M, W) - np.float32([[1, 0, 0], [0, 1, 0]])
    assert abs(resid[0, 0]) < 0.02 and abs(resid[1, 1]) < 0.02, resid
    assert abs(resid[0, 2]) < 3 and abs(resid[1, 2]) < 3, resid


def test_warp_region_inverse_round_trips():
    w, h = 1000, 800
    M = _affine(0.0, 1.08, 30, -15)              # translation+scale: bbox-safe
    region = {"x": 0.2, "y": 0.3, "x2": 0.6, "y2": 0.55}
    fx0, fy0, fx1, fy1 = fr.warp_region(M, region, w, h)
    bx0, by0, bx1, by1 = fr.warp_region(
        fr.invert(M), {"x": fx0, "y": fy0, "x2": fx1, "y2": fy1}, w, h)
    assert np.allclose([bx0, by0, bx1, by1],
                       fr.norm_corners(region), atol=1e-4)


def test_norm_corners_orders_any_input():
    assert fr.norm_corners({"x": 0.6, "y": 0.5, "x2": 0.1, "y2": 0.2}) == \
        (0.1, 0.2, 0.6, 0.5)


def test_discover_chain_rejects_unparseable_name():
    try:
        fr.discover_chain("not-a-timestamp.jpg", "also-bad.jpg")
    except ValueError:
        return
    raise AssertionError("expected ValueError on unparseable filename")


def test_region_change_off_frame_is_nan():
    blank = np.zeros((100, 100, 3), np.uint8)
    far = {"x": 5.0, "y": 5.0, "x2": 6.0, "y2": 6.0}  # entirely off-frame
    val = fr.region_change(blank, blank, far)
    assert val != val, val  # NaN, not 0.0


# --- real-frame: skip if fixtures absent -----------------------------------

def test_real_chain_registration():
    tgt = _fixture("2026-06-07T070020Z.jpg")     # 6h before the reference
    ref = _fixture("2026-06-07T130010Z.jpg")
    res = fr.register_to_reference(tgt, ref)
    assert res["method"] == "chained", res        # too big a gap for one hop
    assert len(res["hops"]) == 6 and all(h["ok"] for h in res["hops"]), res
    assert res["M"] is not None
    rot, scale, tx, ty = fr.decompose(res["M"])
    # Slow wind-nudge drift: tiny rotation, ~unit scale, modest shift.
    assert abs(rot) < 2 and 0.95 < scale < 1.05, (rot, scale)
    assert abs(tx) < 100 and abs(ty) < 100, (tx, ty)


def test_real_adjacent_pair_is_single_hop():
    tgt = _fixture("2026-06-07T120000Z.jpg")     # one hour before reference
    ref = _fixture("2026-06-07T130010Z.jpg")
    res = fr.register_to_reference(tgt, ref)
    assert res["method"] == "direct" and len(res["hops"]) == 1, res
    assert fr.plausible(res["M"], res["inliers"], res["good"])


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
