#!/usr/bin/env python3
"""Standalone experiment: does collapsing a short burst suppress foliage sway?

Self-contained and NON-INTERFERING — it does not import or modify the Pi
capture/upload loop (camera run loop, capture.py, upload.py), never uploads,
and only writes under an output dir you pass. Safe to run alongside production.

Hypothesis: a single overhead frame catches leaves in one random sway
configuration, so single-vs-single region diff is dominated by wind, not real
change. Collapsing a burst (spread over the sway decorrelation window) to a
MEDIAN plate yields a steadier per-time-point image, so median-vs-median diff
drops in swaying-but-unchanged regions while a real change (harvest/moved pot)
stays high. The per-pixel variance across the burst is a free sway map.

Modes:
  synthetic            run here with simulated sway (proves mechanism + code)
  capture  OUTDIR      capture a real burst on the Pi -> raws + plate + sway map
  analyze  DIR1 DIR2   compare two real bursts (single vs median; --register)

Examples:
  .venv/bin/python scripts/sway_experiment.py synthetic
  # on the Pi:
  python scripts/sway_experiment.py capture /tmp/sway_T1 --n 9 --interval 3
  .venv/bin/python scripts/sway_experiment.py analyze /tmp/sway_T1 /tmp/sway_T2 --register
"""
import os
import sys
import glob
import argparse
import numpy as np
import cv2

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)  # allow `python scripts/sway_experiment.py` (not just -m)
import scripts.frame_registration as fr


# --- burst collapse (the core, shared by every mode) -----------------------

def collapse(frames):
    """frames: list of BGR uint8 (same shape). Returns (median_plate, sway_map).
    sway_map = per-pixel temporal stddev (grayscale), the regions that move."""
    stack = np.stack([f.astype(np.float32) for f in frames], axis=0)
    median = np.median(stack, axis=0).astype(np.uint8)
    gray = np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
                     for f in frames], axis=0)
    sway = gray.std(axis=0)
    return median, sway


def region_stat(img_a, img_b, region):
    return fr.region_change(img_a, img_b, region)


def region_mean(gray_map, region):
    """Mean of a single-channel map (e.g. sway) inside a normalised region."""
    h, w = gray_map.shape[:2]
    x0, y0, x1, y1 = fr.norm_corners(region)
    cx0, cx1 = sorted((int(x0 * w), int(x1 * w)))
    cy0, cy1 = sorted((int(y0 * h), int(y1 * h)))
    cx0, cy0 = max(0, cx0), max(0, cy0)
    cx1, cy1 = min(w, cx1), min(h, cy1)
    if cx1 <= cx0 or cy1 <= cy0:
        return float("nan")
    return float(gray_map[cy0:cy1, cx0:cx1].mean())


# --- synthetic mode (runs anywhere; proves the mechanism) ------------------

def _sway_warp(img, rng, amp=3.0, blur=51):
    """Simulate leaf motion: a smooth random displacement field, stronger in the
    lower (plant) half. amp ~ px of leaf movement."""
    h, w = img.shape[:2]
    fx = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (blur, blur), 0)
    fy = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (blur, blur), 0)
    fx /= (np.abs(fx).max() + 1e-6); fy /= (np.abs(fy).max() + 1e-6)
    weight = np.linspace(0.2, 1.0, h)[:, None]  # more sway lower in frame
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    mapx = (gx + fx * amp * weight).astype(np.float32)
    mapy = (gy + fy * amp * weight).astype(np.float32)
    out = cv2.remap(img, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return (out.astype(np.float32) + rng.normal(0, 2, out.shape)).clip(0, 255).astype(np.uint8)


def _synthetic_burst(base, n, seed):
    rng = np.random.default_rng(seed)
    return [_sway_warp(base, rng) for _ in range(n)]


def run_synthetic(n=9):
    base_path = os.path.join(REPO, "scripts/testdata/frames/2026-06-07T130010Z.jpg")
    if not os.path.exists(base_path):
        sys.exit(f"need fixture {base_path}")
    base = cv2.imread(base_path)
    h, w = base.shape[:2]

    # Two bursts of the SAME scene (different sway draws) = no real change.
    b1 = _synthetic_burst(base, n, seed=1)
    b2 = _synthetic_burst(base, n, seed=2)
    # Inject a "harvest" into burst 2: blank a patch so one region truly changes.
    hx0, hy0, hx1, hy1 = int(0.30 * w), int(0.78 * h), int(0.40 * w), int(0.96 * h)
    b2 = [f.copy() for f in b2]
    for f in b2:
        f[hy0:hy1, hx0:hx1] = (60, 60, 60)
    changed_box = {"x": 0.30, "y": 0.78, "x2": 0.40, "y2": 0.96}  # ~unit 35 area

    m1, sway1 = collapse(b1)
    m2, _ = collapse(b2)

    regions = fr.load_regions() + [dict(changed_box, unit_id="HARVEST")]
    print(f"synthetic burst: n={n} per side, simulated sway (amp~3px, lower-heavy)")
    print(f"{'region':>8}  {'single-vs-single':>16}  {'median-vs-median':>16}  "
          f"{'sway(std)':>9}")
    rows = []
    for r in regions:
        single = region_stat(b1[0], b2[0], r)        # one frame each
        med = region_stat(m1, m2, r)                  # plates
        swaymean = region_mean(sway1, r)
        rows.append((r["unit_id"], single, med, swaymean))
    for uid, single, med, sw in sorted(rows, key=lambda x: -x[2]):
        drop = (single - med) / single * 100 if single else 0
        mark = "  <-- real change" if uid == "HARVEST" else ""
        print(f"{str(uid):>8}  {single:16.1f}  {med:16.1f}  {sw:9.1f}"
              f"   ({drop:+.0f}% sway removed){mark}")

    unchanged = [(s, m) for u, s, m, _ in rows if u != "HARVEST"]
    s_mean = sum(s for s, _ in unchanged) / len(unchanged)
    m_mean = sum(m for _, m in unchanged) / len(unchanged)
    print(f"\nunchanged regions: single-vs-single mean={s_mean:.1f}  "
          f"median-vs-median mean={m_mean:.1f}  ({(s_mean-m_mean)/s_mean*100:+.0f}%)")
    print("If median-vs-median is well below single-vs-single on unchanged regions "
          "while\nthe HARVEST region stays high, burst-collapse separates sway from "
          "real change.")
    print("\nNOTE: synthetic sway validates the mechanism + code, NOT real-world "
          "efficacy.\nRun `capture` on the Pi (two bursts ~1h apart) + `analyze` for "
          "the real test.")


# --- capture mode (runs on the Pi; reuses the production camera primitive) --

def run_capture(outdir, n, interval):
    os.makedirs(outdir, exist_ok=True)
    sys.path.insert(0, os.path.join(REPO, "pi"))
    import camera as picam  # the production Camera, not the run loop
    cam = picam.FakeCamera() if os.getenv("SWAY_FAKE") else picam.PiCamera()
    import time
    frames = []
    for i in range(n):
        data = cam.capture()
        p = os.path.join(outdir, f"burst_{i:02d}.jpg")
        with open(p, "wb") as fh:
            fh.write(data)
        arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if arr is not None:
            frames.append(arr)
        print(f"  captured {p}")
        if i < n - 1:
            time.sleep(interval)
    if len(frames) >= 3:
        median, sway = collapse(frames)
        cv2.imwrite(os.path.join(outdir, "plate_median.jpg"), median,
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        cv2.imwrite(os.path.join(outdir, "sway_map.png"),
                    cv2.normalize(sway, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8))
        print(f"wrote plate_median.jpg + sway_map.png to {outdir}")
    print("raws kept in OUTDIR — cull yourself once validated; nothing uploaded.")


# --- analyze mode (two real bursts) ----------------------------------------

def _load_dir(d):
    paths = sorted(glob.glob(os.path.join(d, "burst_*.jpg")))
    if not paths:
        sys.exit(f"no burst_*.jpg in {d}")
    return [cv2.imread(p) for p in paths]


def run_analyze(dir1, dir2, register):
    b1, b2 = _load_dir(dir1), _load_dir(dir2)
    m1, sway1 = collapse(b1)
    m2, _ = collapse(b2)
    s1, s2 = b1[0], b2[0]
    if register:
        res = fr.register_pair(fr.features_gray(m1), fr.features_gray(m2))
        M = res[0]
        if M is not None and fr.plausible(*res):
            h, w = m1.shape[:2]
            m2 = cv2.warpAffine(m2, M, (w, h))
            s2 = cv2.warpAffine(s2, M, (w, h))
            print(f"aligned burst2 plate onto burst1 (inliers={res[1]}/{res[2]})")
        else:
            print("WARNING: could not register the two plates; diffing unaligned")
    regions = fr.load_regions()
    print(f"{'unit':>5}  {'single-vs-single':>16}  {'median-vs-median':>16}  "
          f"{'sway(std)':>9}")
    for r in sorted(regions, key=lambda r: -region_stat(m1, m2, r)
                    if region_stat(m1, m2, r) == region_stat(m1, m2, r) else 0):
        single = region_stat(s1, s2, r)
        med = region_stat(m1, m2, r)
        sw = region_mean(sway1, r)
        print(f"{r['unit_id']:>5}  {single:16.1f}  {med:16.1f}  {sw:9.1f}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    ps = sub.add_parser("synthetic"); ps.add_argument("--n", type=int, default=9)
    pc = sub.add_parser("capture"); pc.add_argument("outdir")
    pc.add_argument("--n", type=int, default=9); pc.add_argument("--interval", type=float, default=3.0)
    pa = sub.add_parser("analyze"); pa.add_argument("dir1"); pa.add_argument("dir2")
    pa.add_argument("--register", action="store_true")
    a = ap.parse_args()
    if a.mode == "synthetic":
        run_synthetic(a.n)
    elif a.mode == "capture":
        run_capture(a.outdir, a.n, a.interval)
    elif a.mode == "analyze":
        run_analyze(a.dir1, a.dir2, a.register)


if __name__ == "__main__":
    main()
