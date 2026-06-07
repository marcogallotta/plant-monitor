#!/usr/bin/env python3
"""Finlayson illuminant-invariant ("intrinsic") image, tested on a known harvest.

Photometric diffs (grad) and ExG vegetation-coverage both failed on the
2026-06-07 15:00->16:00 pair because the confound is illuminant COLOUR change
(direct sun ~5500K vs shadow lit by blue sky ~10000K), which shifts the R:G:B
ratio. Normalised-rgb removes intensity, not colour, so it can't fix it.

Finlayson's 1-D invariant IS invariant to illuminant colour+intensity: in 2-D
log-chromaticity, changing the illuminant moves a pixel along a camera-specific
line; projecting onto the orthogonal direction (angle theta) removes it. theta is
found once by entropy minimisation and then applied to BOTH frames so they are
comparable. Shadows/sun largely cancel; a harvest (leaf -> soil/pot, a real
reflectance change) survives.

    .venv/bin/python scripts/finlayson_experiment.py [REF TGT]
"""
import os, sys
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.frame_registration as fr

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PH = os.path.join(REPO, "data", "photos")
DEF_REF = os.path.join(PH, "2026-06-07T150010Z.jpg")
DEF_TGT = os.path.join(PH, "2026-06-07T160010Z.jpg")
HARVESTED = {"Genovese basil", "Rocket"}
NAMES = {36:"Birdseye",39:"Chives",40:"Cilantro",41:"Cilantro root",4:"Dill",5:"Fr.tarragon",
6:"Garlic chives",16:"Genovese basil",34:"Hangijiao4",35:"Hangijiao7",21:"Lemongrass",
17:"Moroccan mint",20:"Parsley",19:"Peppermint",7:"Rau ram",23:"Rocket",1:"Rosemary",
37:"Sage",8:"Sorrel",15:"Thai basil",3:"Thai basil vend",38:"Thyme",18:"Welsh onion"}

# orthonormal basis for the plane orthogonal to [1,1,1] (the log-chromaticity plane)
U = np.array([[1/np.sqrt(2), -1/np.sqrt(2), 0.0],
              [1/np.sqrt(6),  1/np.sqrt(6), -2/np.sqrt(6)]])


def log_chrom(bgr):
    """HxWx2 log-chromaticity + a validity mask (drop near-black/saturated)."""
    b = bgr.astype(np.float32) + 1.0
    R, G, B = b[..., 2], b[..., 1], b[..., 0]
    gm = np.cbrt(R * G * B)
    rho = np.stack([np.log(R/gm), np.log(G/gm), np.log(B/gm)], axis=-1)
    chi = rho @ U.T
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    valid = (g > 15) & (g < 245)
    return chi, valid


def _entropy(vals):
    if vals.size < 50:
        return 1e9
    # Scott bin width, robust to scale
    bw = 3.5 * vals.std() / (vals.size ** (1/3) + 1e-9)
    if bw <= 1e-6:
        return 1e9
    bins = max(16, int((vals.max() - vals.min()) / bw))
    h, _ = np.histogram(vals, bins=min(bins, 512))
    p = h[h > 0] / h.sum()
    return float(-(p * np.log(p)).sum())


def find_theta(chi, valid):
    """Illuminant-invariant projection angle: the one minimising entropy."""
    v = chi[valid]
    best, bt = 1e18, 0.0
    for deg in range(0, 180, 2):
        t = np.deg2rad(deg)
        e = _entropy(v[:, 0]*np.cos(t) + v[:, 1]*np.sin(t))
        if e < best:
            best, bt = e, t
    return bt


def invariant(chi, theta):
    I = chi[..., 0]*np.cos(theta) + chi[..., 1]*np.sin(theta)
    return cv2.normalize(I, None, 0, 255, cv2.NORM_MINMAX)


def _crop(img, r):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = fr.norm_corners(r)
    cx0, cx1 = sorted((int(round(x0*w)), int(round(x1*w))))
    cy0, cy1 = sorted((int(round(y0*h)), int(round(y1*h))))
    cx0, cy0 = max(0, cx0), max(0, cy0); cx1, cy1 = min(w, cx1), min(h, cy1)
    if cx1-cx0 < 3 or cy1-cy0 < 3:
        return None
    return img[cy0:cy1, cx0:cx1].astype(np.float32)


def _ncc(a, b):
    a, b = a-a.mean(), b-b.mean()
    da, db = np.sqrt((a*a).sum()), np.sqrt((b*b).sum())
    return 1.0 if da < 1e-6 or db < 1e-6 else float((a*b).sum()/(da*db))


def _gm(p):
    return cv2.magnitude(cv2.Sobel(p, cv2.CV_32F, 1, 0, 3), cv2.Sobel(p, cv2.CV_32F, 0, 1, 3))


def main():
    ref_p = sys.argv[1] if len(sys.argv) > 2 else DEF_REF
    tgt_p = sys.argv[2] if len(sys.argv) > 2 else DEF_TGT
    ref, tgt = cv2.imread(ref_p), cv2.imread(tgt_p)

    res = fr.register_pair(fr.features_gray(ref), fr.features_gray(tgt))
    if res[0] is not None and fr.plausible(*res):
        h, w = ref.shape[:2]; tgt = cv2.warpAffine(tgt, res[0], (w, h))
        print(f"aligned (inliers={res[1]}/{res[2]})")

    cr, vr = log_chrom(ref)
    theta = find_theta(cr, vr)          # calibrate ONCE on the reference frame
    print(f"invariant angle theta = {np.rad2deg(theta):.0f} deg")
    Ir = invariant(cr, theta)
    ct, _ = log_chrom(tgt)
    It = invariant(ct, theta)           # SAME theta -> comparable
    cv2.imwrite("/tmp/inv_ref.jpg", Ir.astype(np.uint8))
    cv2.imwrite("/tmp/inv_tgt.jpg", It.astype(np.uint8))

    rows = []
    for r in fr.load_regions():
        a, b = _crop(Ir, r), _crop(It, r)
        if a is None or b is None or a.shape != b.shape:
            continue
        rows.append((r["unit_id"], float(np.abs(a-b).mean()),       # raw on invariant
                     1.0-_ncc(_gm(a), _gm(b))))                       # grad on invariant
    def rank(idx, name):
        order = sorted(rows, key=lambda r: -r[1+idx])
        seen = {}
        for i, rr in enumerate(order, 1):
            seen.setdefault(NAMES.get(rr[0], rr[0]), i)
        return seen.get(name)
    n = len({NAMES.get(r[0]) for r in rows})
    print(f"\n{'unit':>16} {'rawINV':>7} {'gradINV':>8}")
    for uid, raw, grad in sorted(rows, key=lambda r: -r[2])[:8]:
        mk = "  <== harvested" if NAMES.get(uid) in HARVESTED else ""
        print(f"{NAMES.get(uid,uid):>16} {raw:7.1f} {grad:8.3f}{mk}")
    print(f"\nharvested-plant ranks (of {n} units):")
    for name in HARVESTED:
        print(f"  {name:>16}: rawINV #{rank(0,name)}   gradINV #{rank(1,name)}")
    print("invariant images -> /tmp/inv_ref.jpg /tmp/inv_tgt.jpg")


if __name__ == "__main__":
    main()
