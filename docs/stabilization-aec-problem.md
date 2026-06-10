# Stabilization: AEC sunrise failure — what was tried and why it didn't work

## The problem

Frames captured during the **sunrise AEC window** (~07:00–12:00 UTC, ~09:00–14:00 CEST) have
`stab_status="failed"` and no transform matrix.  The Pi camera's auto-exposure compensates as
the scene brightens, so these frames look overexposed relative to the reference (mid-afternoon,
full exposure, good contrast).  ORB feature matching breaks across this illumination boundary and
the chain registration can't reach these frames.

## What was tried

### Attempt 1: raise RESID_GATE_FRAC and widen ECC fallback

Raised `RESID_GATE_FRAC` 0.02 → 0.04 and added an ECC fallback inside `anchor_frame` using a
registered neighbour's matrix as warm-start.  Also added a rescue pass after the main loop with
unbounded neighbour search.

**Result:** rescued one stranded post-AEC frame (June 10 13:00), but the 6 deep AEC frames
(07:00–12:00) still failed.  ECC with a warm start to the anchor converges for near-boundary
frames but not for frames where the illumination gap to the reference is large.

### Attempt 2: chain ECC + gradient (Sobel) images, drop ORB gate

In the rescue pass, added a second strategy: register frame *i* against its nearest temporal
neighbour *j* (a much smaller illumination gap than the anchor) using Sobel gradient-magnitude
images, then compose `M[j] ∘ M_rel` to get the full i→anchor transform.  Also dropped the ORB
residual gate from the rescue pass entirely, since ORB is the very thing that fails on AEC frames.

**Result:** all 6 AEC frames showed `registered` with plausible-looking parameters (rot ~0.7°,
t consistent with neighbours).  **But the timelapse became jumpy — the new registrations were
geometrically wrong despite passing plausibility + temporal-consistency checks.**

### Why removing the ORB gate backfired

The ORB residual gate (`residual_to_ref`) is the *only* check that measures actual spatial
alignment.  Without it:

- ECC can converge to a local minimum that looks plausible (small rotation, nearby translation)
  but places the frame at the wrong position.
- Plausibility (rotation < 2°) and consistency (< 30 px from warm start) can both pass for a
  wrong local minimum if the minimum is geometrically small but photometrically confusing.
- Gradient images reduce but don't eliminate local minima: the Sobel magnitude of an overexposed
  scene still has spurious dominant edges (blown-out regions create artefact edges).

The ORB gate was correctly rejecting these wrong transforms.  The problem is that it also
rejects correct transforms for AEC frames — so we need a gate that:

1. Is illumination-robust (unlike ORB), AND
2. Actually measures spatial alignment (unlike plausibility/consistency alone).

## What a real fix would need

Step 4 below is **not** nice-to-have — it is the **replacement** for `residual_to_ref` in the
rescue path.  The current circuit is broken circularly:

```text
ECC handles exposure jump → ORB rejects because exposure jump remains
```

Gradient `computeECC` breaks the cycle: illumination-robust AND measures actual spatial alignment.

### Acceptance stack for ECC rescue frames

```text
1. ECC converged (no exception from findTransformECC)
2. rho_warped = cv2.computeECC(gradmag(ref), gradmag(warped_frame), stable_mask) >= floor
3. rho_warped >= rho_identity + min_gain
   (identity = no warp, proves ECC actually improved alignment)
4. Transform sanity: translation within expected mount drift, rotation < ~2°
5. Temporal consistency: < 30 px from nearest registered neighbour
```

### Gradient magnitude preprocessing

```python
def gradmag(gray):
    g = cv2.GaussianBlur(gray, (5, 5), 0)
    gx = cv2.Scharr(g, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(g, cv2.CV_32F, 0, 1)
    mag = cv2.magnitude(gx, gy)
    mag = np.log1p(mag)          # compress blown-edge artefacts from overexposure
    return mag.astype(np.float32)
```

### Mask

Score only **stable, non-plant regions** (pot rims, tray, shelf, sensor, markers).  Plant foliage
grows, wilts, and casts changing shadows — including it degrades the score for correct transforms.
Use `reference_regions.json` controls.  Also exclude blown-out (>248) and near-black (<8) pixels
in either image, and warp-border pixels (where `warpAffine` inserts zeros).

### Calibration

Calibrate on **three groups**, not two:

- A: known-good accepted non-AEC frames
- B: AEC identity (no warp)
- C: the Attempt 2 bad transforms that looked plausible but caused jumps

Threshold must separate **A from C**, not just A from B.

Note: a correct AEC warp may not reach the same `rho_good` as normal daylight frames because
overexposure destroys real edge information.  The goal is: `rho_correct_AEC > rho_identity + gain`
and `rho_correct_AEC >> rho_bad_local_minimum`.

## Current state

Restored to ALGO_REV=3, RESID_GATE_FRAC=0.04, gate inside `anchor_frame`.  AEC frames are
`failed` — displayed without stabilization in the timelapse.  Non-AEC frames are all correctly
registered (47/87 as of June 2026).

The AEC stabilization problem is unsolved.  A future attempt should implement the gradient
`computeECC` gate (step 4 above) and calibrate thresholds on real frames before accepting any
ECC result that the ORB gate would reject.
