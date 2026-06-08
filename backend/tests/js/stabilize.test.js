import { describe, it, expect } from 'vitest';
import { parseStab, commonCrop, canvasTransform } from '@/stabilize.js';

const IDENTITY = [1, 0, 0, 0, 1, 0]; // [m00,m01,m02,m10,m11,m12]

// ── parseStab ─────────────────────────────────────

describe('parseStab', () => {
  it('extracts a valid payload', () => {
    expect(parseStab({ stab_matrix: IDENTITY, stab_ref_w: 1600, stab_ref_h: 900 }))
      .toEqual({ m: IDENTITY, refW: 1600, refH: 900 });
  });

  it('returns null when matrix is missing/null (non-Pi or failed frame)', () => {
    expect(parseStab({ stab_matrix: null, stab_ref_w: 1600, stab_ref_h: 900 })).toBeNull();
    expect(parseStab({})).toBeNull();
    expect(parseStab(null)).toBeNull();
  });

  it('returns null on a malformed matrix or missing dims', () => {
    expect(parseStab({ stab_matrix: [1, 0, 0], stab_ref_w: 1600, stab_ref_h: 900 })).toBeNull();
    expect(parseStab({ stab_matrix: IDENTITY, stab_ref_w: 0, stab_ref_h: 900 })).toBeNull();
  });
});

// ── commonCrop ─────────────────────────────────────

describe('commonCrop', () => {
  it('is the full frame when every transform is identity', () => {
    const s = { m: IDENTITY, refW: 1600, refH: 900 };
    expect(commonCrop([s, s])).toEqual({ x0: 0, y0: 0, x1: 1, y1: 1 });
  });

  it('falls back to the full frame when there is nothing to intersect', () => {
    expect(commonCrop([null, null])).toEqual({ x0: 0, y0: 0, x1: 1, y1: 1 });
  });

  it('crops by a pure translation (frame shifted right+down loses left+top)', () => {
    // m02=+160px right (=0.1 of 1600), m12=+90px down (=0.1 of 900).
    const s = { m: [1, 0, 160, 0, 1, 90], refW: 1600, refH: 900 };
    const crop = commonCrop([s]);
    expect(crop.x0).toBeCloseTo(0.1, 6);
    expect(crop.y0).toBeCloseTo(0.1, 6);
    expect(crop.x1).toBeCloseTo(1, 6);
    expect(crop.y1).toBeCloseTo(1, 6);
  });

  it('intersects opposing shifts to the inner common region', () => {
    const right = { m: [1, 0, 160, 0, 1, 0], refW: 1600, refH: 900 };
    const left = { m: [1, 0, -160, 0, 1, 0], refW: 1600, refH: 900 };
    const crop = commonCrop([right, left]);
    expect(crop.x0).toBeCloseTo(0.1, 6);
    expect(crop.x1).toBeCloseTo(0.9, 6);
  });

  it('guards against a degenerate intersection (returns full frame)', () => {
    const a = { m: [1, 0, 1600, 0, 1, 0], refW: 1600, refH: 900 }; // shifted fully off
    expect(commonCrop([a])).toEqual({ x0: 0, y0: 0, x1: 1, y1: 1 });
  });
});

// ── canvasTransform ─────────────────────────────────────

describe('canvasTransform', () => {
  const full = { x0: 0, y0: 0, x1: 1, y1: 1 };

  it('identity at native res + full crop just scales source to canvas', () => {
    const stab = { m: IDENTITY, refW: 1600, refH: 900 };
    const [a, b, c, d, e, f] = canvasTransform(stab, full, 1600, 800, 450);
    expect(a).toBeCloseTo(0.5, 6); // 800/1600
    expect(d).toBeCloseTo(0.5, 6); // 450/900
    expect([b, c, e, f]).toEqual([0, 0, 0, 0]);
  });

  it('rescales the matrix when the served image is downscaled (s2r)', () => {
    // Source served at 800px wide, reference space is 1600 -> s2r = 2.
    const stab = { m: IDENTITY, refW: 1600, refH: 900 };
    const [a] = canvasTransform(stab, full, 800, 1600, 900);
    expect(a).toBeCloseTo(2, 6); // (1600/1600)*(1600/800)
  });

  it('maps a translation into a canvas-pixel offset against the crop', () => {
    // Frame shifted +160px right; crop removes that left margin (x0=0.1).
    const stab = { m: [1, 0, 160, 0, 1, 0], refW: 1600, refH: 900 };
    const crop = { x0: 0.1, y0: 0, x1: 1, y1: 1 };
    // cropW=0.9 -> canvas covers 0.9*1600=1440 ref px across cw.
    const cw = 1440, ch = 900;
    const [, , , , e] = canvasTransform(stab, crop, 1600, cw, ch);
    // kx = 1440/(1600*0.9) = 1 ; e = kx*m02 - x0*cw/cropW = 160 - 0.1*1440/0.9 = 0.
    expect(e).toBeCloseTo(0, 6);
  });
});
