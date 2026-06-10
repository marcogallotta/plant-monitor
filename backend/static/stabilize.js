// Tilt/drift stabilization for timelapse + compare.
//
// The backend (scripts/compute_stabilization.py) stores a per-photo 2x3 affine
// `stab_matrix` mapping the frame's pixels (at reference resolution stab_ref_w x
// stab_ref_h) onto a canonical reference frame. Warping each frame by its matrix
// puts the whole set into one alignment, so the only motion left in a timelapse
// is real (growth, sway) rather than mount wobble.
//
// The expensive registration is precomputed; this module is just the cheap
// display-time warp, done on a <canvas> via setTransform. Pure functions
// (parseStab/commonCrop/canvasTransform) are unit-tested; drawStabilized is the
// thin DOM wrapper.

// Pull the stabilization payload off a photo, or null if it can't be stabilized
// (non-Pi source, or registration failed -> matrix is null).
export function parseStab(photo) {
  const m = photo && photo.stab_matrix;
  if (!Array.isArray(m) || m.length !== 6) return null;
  if (!photo.stab_ref_w || !photo.stab_ref_h) return null;
  return { m, refW: photo.stab_ref_w, refH: photo.stab_ref_h };
}

// Warp the four corners of a full frame (in reference-resolution pixels) through
// its matrix and return them in normalised reference space [0,1].
function coveredCorners({ m, refW, refH }) {
  const [a, c, e, b, d, f] = m; // row-major [m00,m01,m02,m10,m11,m12]
  const warp = (x, y) => [(a * x + c * y + e) / refW, (b * x + d * y + f) / refH];
  return {
    tl: warp(0, 0), tr: warp(refW, 0), br: warp(refW, refH), bl: warp(0, refH),
  };
}

// Largest axis-aligned rect (normalised) common to every stabilized frame, so
// the warp's exposed black borders are cropped off. Falls back to the full frame
// when there's nothing to intersect or the intersection is degenerate.
//
// Assumes the transforms are near-axis-aligned — translation + small rotation +
// tiny scale, which is exactly the fixed-mount drift this is built for. It is NOT
// correct for perspective or large shear (the inner-rect approximation breaks);
// compute_stabilization only ever emits rigid similarity transforms.
export function commonCrop(stabs) {
  let x0 = 0, y0 = 0, x1 = 1, y1 = 1;
  let any = false;
  for (const s of stabs) {
    if (!s) continue;
    any = true;
    const { tl, tr, br, bl } = coveredCorners(s);
    // Inner rect inside the (near-axis-aligned) covered quad.
    x0 = Math.max(x0, tl[0], bl[0]);
    x1 = Math.min(x1, tr[0], br[0]);
    y0 = Math.max(y0, tl[1], tr[1]);
    y1 = Math.min(y1, bl[1], br[1]);
  }
  if (!any || x1 - x0 < 0.1 || y1 - y0 < 0.1) return { x0: 0, y0: 0, x1: 1, y1: 1 };
  return { x0, y0, x1, y1 };
}

// The canvas setTransform tuple [a,b,c,d,e,f] that draws a source image (drawn at
// 0,0, natural size naturalW x naturalH) stabilized and cropped into a cw x ch canvas.
// Composes: source px -> reference px (matrix, rescaled per-axis for the served variant)
// -> normalised -> crop window -> canvas px. Separate X/Y scale factors are required
// because served images can have a different aspect ratio from the reference (e.g. a
// rotated or resized variant). Using only the width scale for Y (the previous approach)
// causes vertical misalignment whenever the two frames differ in height.
export function canvasTransform({ m, refW, refH }, crop, naturalW, naturalH, cw, ch) {
  const [m00, m01, m02, m10, m11, m12] = m;
  const sx = refW / naturalW;                  // source X px -> reference X px
  const sy = refH / naturalH;                  // source Y px -> reference Y px
  const cropW = crop.x1 - crop.x0, cropH = crop.y1 - crop.y0;
  const kx = cw / (refW * cropW), ky = ch / (refH * cropH);
  return [
    kx * m00 * sx,                             // a
    ky * m10 * sx,                             // b
    kx * m01 * sy,                             // c
    ky * m11 * sy,                             // d
    kx * m02 - crop.x0 * cw / cropW,           // e
    ky * m12 - crop.y0 * ch / cropH,           // f
  ];
}

// Draw a loaded image onto `canvas`, stabilized to `crop`. Sizes the canvas
// backing store to the crop aspect at `dispW` so output is crisp. Returns true
// if it drew stabilized, false if it couldn't (caller should fall back to raw).
export function drawStabilized(canvas, img, stab, crop, dispW = 1100) {
  if (!stab || !img.naturalWidth) return false;
  const cropW = crop.x1 - crop.x0, cropH = crop.y1 - crop.y0;
  const aspect = (cropW * stab.refW) / (cropH * stab.refH);
  const cw = Math.round(dispW);
  const ch = Math.round(dispW / aspect);
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, cw, ch);
  const [a, b, c, d, e, f] = canvasTransform(stab, crop, img.naturalWidth, img.naturalHeight, cw, ch);
  ctx.setTransform(a, b, c, d, e, f);
  ctx.drawImage(img, 0, 0);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  return true;
}

// Per-canvas render token: with fast A/B flicker, several stabilized renders can
// be in flight at once; only the most recent one for a given canvas may draw, so
// a slow earlier load can't clobber a newer frame.
let _renderSeq = 0;
const _latestRender = new WeakMap();

// Show one photo in a view that has both an <img> (raw) and a <canvas>
// (stabilized). When `stabilize` is on and the photo has a matrix, the image is
// loaded into a PRIVATE Image (so overlapping renders can't stomp a shared
// onload) and drawn warped onto the canvas; otherwise the raw <img> is shown.
// Rotation (0/90/180/270) is applied as a CSS transform on whichever is visible.
// `url` lets callers pass an oriented or cache-busted variant; defaults to the
// photo's plain url.
export function renderFrame(imgEl, canvasEl, photo, crop, opts = {}) {
  const { stabilize = true, rotation = photo.rotation || 0, url = photo.url } = opts;
  const stab = (stabilize && canvasEl) ? parseStab(photo) : null;
  const rot = rotation ? `rotate(${rotation}deg)` : '';

  const showRaw = () => {
    if (imgEl.dataset.frameUrl !== url) { imgEl.src = url; imgEl.dataset.frameUrl = url; }
    imgEl.style.transform = rot;
    imgEl.style.display = 'block';
    if (canvasEl) canvasEl.style.display = 'none';
  };
  if (!stab) { showRaw(); return; }

  const token = ++_renderSeq;
  _latestRender.set(canvasEl, token);
  const loader = new Image();
  loader.onload = () => {
    if (_latestRender.get(canvasEl) !== token) return;   // superseded by a newer render
    if (drawStabilized(canvasEl, loader, stab, crop)) {
      canvasEl.style.transform = rot;
      canvasEl.style.display = 'block';
      imgEl.style.display = 'none';
    } else {
      showRaw();
    }
  };
  loader.src = url;
}
