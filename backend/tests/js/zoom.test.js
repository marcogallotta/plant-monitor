import { describe, it, expect, beforeAll } from 'vitest';
import { state } from '@/state.js';

// zoom.js has top-level DOM queries and event listeners, so we must set up
// the required elements before importing the module.
let visualToStored;
beforeAll(async () => {
  document.body.innerHTML = '<div id="zoom-viewport"></div>';
  ({ visualToStored } = await import('@/zoom.js'));
});

describe('visualToStored', () => {
  it('rotation 0: returns coords unchanged', () => {
    state.currentRotation = 0;
    expect(visualToStored(0.3, 0.7)).toEqual({x: 0.3, y: 0.7});
  });

  it('rotation 90: maps (rx, ry) → (ry, 1-rx)', () => {
    state.currentRotation = 90;
    expect(visualToStored(0.3, 0.7)).toEqual({x: 0.7, y: 0.7});
  });

  it('rotation 180: maps (rx, ry) → (1-rx, 1-ry)', () => {
    state.currentRotation = 180;
    expect(visualToStored(0.25, 0.75)).toEqual({x: 0.75, y: 0.25});
  });

  it('rotation 270: maps (rx, ry) → (1-ry, rx)', () => {
    state.currentRotation = 270;
    expect(visualToStored(0.25, 0.75)).toEqual({x: 0.25, y: 0.25});
  });

  it('clamps values below 0 to 0', () => {
    state.currentRotation = 0;
    const {x, y} = visualToStored(-0.1, -0.5);
    expect(x).toBe(0);
    expect(y).toBe(0);
  });

  it('clamps values above 1 to 1', () => {
    state.currentRotation = 0;
    const {x, y} = visualToStored(1.2, 1.5);
    expect(x).toBe(1);
    expect(y).toBe(1);
  });

  it('corners map correctly for rotation 90', () => {
    state.currentRotation = 90;
    // top-left visual (0,0) → bottom-left stored (0,1)
    expect(visualToStored(0, 0)).toEqual({x: 0, y: 1});
    // top-right visual (1,0) → top-left stored (0,0)
    expect(visualToStored(1, 0)).toEqual({x: 0, y: 0});
  });
});
