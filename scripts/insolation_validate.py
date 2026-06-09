#!/usr/bin/env python3
"""Validate radiometric insolation-from-camera on OPEN-SUN reference patches.

History: naive mean-luminance was falsified (Spearman -0.43) because the camera
AUTO-EXPOSES, flattening brightness. The white sensor cap looked like a clean
fixed-albedo reference but is UNDER THE SHADE NET, whose fine dappling makes a
point patch read fleck-noise, not insolation. Fix: log exposure/gain at capture
(pi/capture.py, done) and validate on a patch in OPEN sun.

This compares, across the daytime arc, NAIVE patch brightness vs RADIOMETRIC
brightness = patch / (exposure_us * analogue_gain * digital_gain), against the
camera's own whole-frame Lux. Result (2026-06-08, 04-10Z): radiometric tracks the
solar arc at Spearman +0.96..+1.00 across three open-sun patches; naive is
flat/anti (-0.36..+0.54). => insolation-from-camera is VIABLE on open-sun targets;
net-shaded regions use the canopy-integrating region-average. See
docs/vision-tagging.md "insolation".

Caveat: picamLux itself derives from exposure*gain (mild circularity), but three
patches agree and picamLux ~= Flower-Care lux in the clean morning regime.

    .venv/bin/python scripts/insolation_validate.py 'data/photos/2026-06-08T0[4-9]*Z.jpg' 'data/photos/2026-06-08T100000Z.jpg'
"""
import os, sys, json, glob, argparse
import numpy as np, cv2

# Open-sun reference patches (normalised), away from the net. Override with --patch.
PATCHES = {"tile_C": (0.26, 0.89), "tile_L": (0.13, 0.88), "potrim": (0.33, 0.80)}
HALF = 0.018  # half box size (normalised)


def patch_bright(im, cx, cy):
    h, w = im.shape[:2]
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
    sub = g[int((cy - HALF) * h):int((cy + HALF) * h),
            int((cx - HALF) * w):int((cx + HALF) * w)].ravel()
    if sub.size == 0:
        return np.nan
    return float(np.sort(sub)[int(0.6 * len(sub)):].mean())   # brightest 40% = sunlit


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", nargs="+")
    a = ap.parse_args()
    paths = sorted(sum((glob.glob(f) for f in a.frames), []))
    rows = []
    for p in paths:
        try:
            c = json.load(open(p.replace(".jpg", ".json"))).get("camera")
        except FileNotFoundError:
            continue
        if not c or not c.get("exposure_us"):
            continue
        im = cv2.imread(p)
        eg = c["exposure_us"] * c["analogue_gain"] * c.get("digital_gain", 1.0)
        b = os.path.basename(p)
        row = {"t": b[11:13] + ":" + b[13:15], "lux": c.get("lux")}
        for name, (cx, cy) in PATCHES.items():
            b = patch_bright(im, cx, cy)
            row[name + "_naive"], row[name + "_radio"] = b, b / eg * 1e6
        rows.append(row)
    if len(rows) < 3:
        sys.exit("need >=3 frames with camera metadata")

    print(f"{'time':>6} {'picamLux':>9}", end="")
    for n in PATCHES:
        print(f" | {n+' naive':>11} {n+' radio':>11}", end="")
    print()
    for r in rows:
        print(f"{r['t']:>6} {r['lux']:9.0f}", end="")
        for n in PATCHES:
            print(f" | {r[n+'_naive']:11.0f} {r[n+'_radio']:11.1f}", end="")
        print()

    lux = np.array([r["lux"] for r in rows])
    print("\nSpearman vs picamLux (radiometric should be HIGH +, naive ~0/negative):")
    for n in PATCHES:
        nv = np.array([r[n + "_naive"] for r in rows])
        rd = np.array([r[n + "_radio"] for r in rows])
        print(f"  {n:>8}: naive {spearman(nv, lux):+.2f}   radiometric {spearman(rd, lux):+.2f}")


if __name__ == "__main__":
    main()
