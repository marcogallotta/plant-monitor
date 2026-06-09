#!/usr/bin/env python3
"""Does per-region camera luminance measure insolation? Tested against ground truth.

CLAIM (from the water-balance design): the diurnal lighting that confounds change
detection is also a free per-region INSOLATION signal — bright region = sunlit,
dark = shaded — so mean region luminance over the day reads out sun exposure, the
evaporative-demand term.

TEST: the Cilantro pot has a Xiaomi Flower Care with ground-truth `light_lux`.
Correlate the Cilantro region's mean grayscale luminance across the day's frames
against that lux.

RESULT (2026-06-07): FALSIFIED. Spearman = -0.43 (anti-correlated). Mean 8-bit
luminance does NOT measure insolation, because:
  1. the camera AUTO-EXPOSES (sunlit scene stopped down -> not brighter in 8-bit);
  2. saved frames carry NO exposure EXIF (plate re-encoded from numpy strips it),
     so auto-exposure can't be normalised out post-hoc;
  3. the lux reference is a dappled-shade POINT sensor swinging x128 hour-to-hour.
See docs/vision-tagging.md "Insolation ... TESTED ... FALSIFIED" for the path
forward (log ExposureTime/AnalogueGain at capture, or detect sun-vs-shadow by
spatial pattern instead of mean brightness).

Usage (needs LAN access to the esp32 sensor server + the day's frames on disk):
    SENSOR_API_KEY=... .venv/bin/python scripts/insolation_experiment.py
"""
import os, sys, glob, json, datetime as dt, urllib.request, ssl
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.frame_registration as fr

# NOTE (2026-06-09): falsified, frozen experiment on the 2026-06-07 window — that data
# predates the Pi cutover and came from the corrupt esp32 ingestion. Intentionally NOT
# migrated to the in-repo Flower Care source (re-running would only reproduce the
# falsified result on a window with no clean data). Kept as a record, not a live tool.
SENSOR_URL = os.getenv("SENSOR_API_URL", "https://laptop.local:8000")
KEY = os.getenv("SENSOR_API_KEY", "")
CILANTRO_SENSOR = "3ee7f8a3-9811-45ce-8296-c909a104952b"
CILANTRO_UNITS = (40, 41)          # Cilantro + Cilantro root regions
REF = "data/photos/2026-06-07T130010Z.jpg"
DAY_GLOB = "data/photos/2026-06-07T*Z.jpg"


def fetch_lux():
    url = (f"{SENSOR_URL}/sensors/{CILANTRO_SENSOR}/readings"
           f"?start_ts=2026-06-07T06:00:00Z&end_ts=2026-06-07T18:00:00Z&max_points=50")
    req = urllib.request.Request(url, headers={"X-Api-Key": KEY})
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    rows = json.load(urllib.request.urlopen(req, context=ctx))
    return sorted((_min(r["timestamp"]), r["light_lux"]) for r in rows)


def _min(ts):
    t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return t.hour * 60 + t.minute


def region_lum(im, r, w, h):
    x0, y0, x1, y1 = fr.norm_corners(r)
    cx0, cx1 = sorted((int(x0 * w), int(x1 * w)))
    cy0, cy1 = sorted((int(y0 * h), int(y1 * h)))
    g = cv2.cvtColor(im[max(0, cy0):cy1, max(0, cx0):cx1], cv2.COLOR_BGR2GRAY)
    return float(g.mean())


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    ref = cv2.imread(REF); h, w = ref.shape[:2]
    regs = {}
    for r in fr.load_regions():
        regs.setdefault(r["unit_id"], []).append(r)
    lux = fetch_lux()
    luxmins = [m for m, _ in lux]

    cam, matched_lux = [], []
    for p in sorted(glob.glob(DAY_GLOB)):
        im = cv2.imread(p)
        if "T130010Z" not in p:
            res = fr.register_pair(fr.features_gray(ref), fr.features_gray(im))
            if res[0] is not None and fr.plausible(*res):
                im = cv2.warpAffine(im, res[0], (w, h))
        ts = os.path.basename(p)[11:17]; m = int(ts[:2]) * 60 + int(ts[2:4])
        lums = [region_lum(im, r, w, h) for u in CILANTRO_UNITS for r in regs.get(u, [])]
        i = min(range(len(luxmins)), key=lambda k: abs(luxmins[k] - m))
        cam.append(np.mean(lums)); matched_lux.append(lux[i][1])
        print(f"  {m//60:02d}:{m%60:02d}  camLum={cam[-1]:6.1f}  lux={lux[i][1]:6d}")

    cam, lx = np.array(cam), np.array(matched_lux, float)
    print(f"\nSpearman(camLum, lux) = {spearman(cam, lx):+.3f}  "
          f"(expected ~+1 if luminance measured insolation; got anti-correlation)")
    print("=> naive mean-luminance insolation is FALSIFIED (auto-exposure; see module docstring)")


if __name__ == "__main__":
    main()
