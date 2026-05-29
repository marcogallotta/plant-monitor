import { vi, describe, it, expect, beforeAll, beforeEach } from 'vitest';

// zoom.js has top-level DOM queries and event listeners, so we must set up
// the required elements before importing the module.
let visualToStored, applyTransform, resetZoom;
let state;
beforeAll(async () => {
  document.body.innerHTML = `
    <div id="zoom-viewport">
      <div id="modal-img-wrap" style="position:relative">
        <img id="modal-img">
        <div id="rect-preview" style="display:none;position:absolute"></div>
      </div>
    </div>
  `;
  ({ visualToStored, applyTransform, resetZoom } = await import('@/zoom.js'));
  ({ state } = await import('@/state.js'));
});

beforeEach(() => {
  state.zoom = 1; state.panX = 0; state.panY = 0;
  state.isPanning = false; state.wasDrag = false; state.panStart = null;
  state.isDrawingRect = false; state.rectStart = null;
  state.currentRotation = 0; state.currentPhotoId = null;
  document.getElementById('rect-preview').style.display = 'none';
  document.getElementById('modal-img-wrap').style.transform = '';
  document.getElementById('zoom-viewport').classList.remove('grabbing', 'drawing');
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

// ── applyTransform ────────────────────────────────────────

describe('applyTransform', () => {
  it('sets transform on #modal-img-wrap with translate, scale, and rotate', () => {
    state.panX = 10; state.panY = 20; state.zoom = 1.5; state.currentRotation = 90;
    applyTransform();
    const t = document.getElementById('modal-img-wrap').style.transform;
    expect(t).toContain('translate(10px, 20px)');
    expect(t).toContain('scale(1.5)');
    expect(t).toContain('rotate(90deg)');
  });
});

// ── resetZoom ─────────────────────────────────────────────

describe('resetZoom', () => {
  it('resets zoom and pan to defaults', () => {
    state.zoom = 3; state.panX = 50; state.panY = 30;
    resetZoom();
    expect(state.zoom).toBe(1);
    expect(state.panX).toBe(0);
    expect(state.panY).toBe(0);
  });

  it('clears rect drawing state', () => {
    state.isDrawingRect = true;
    state.rectStart = {x: 0.5, y: 0.5};
    resetZoom();
    expect(state.isDrawingRect).toBe(false);
    expect(state.rectStart).toBeNull();
  });

  it('hides rect-preview', () => {
    document.getElementById('rect-preview').style.display = 'block';
    resetZoom();
    expect(document.getElementById('rect-preview').style.display).toBe('none');
  });
});

// ── wheel handler ─────────────────────────────────────────

describe('wheel handler', () => {
  it('zooms in on scroll up (deltaY < 0)', () => {
    document.getElementById('zoom-viewport').dispatchEvent(
      new WheelEvent('wheel', {deltaY: -100, bubbles: true, cancelable: true}),
    );
    expect(state.zoom).toBeGreaterThan(1);
  });

  it('zooms out on scroll down (deltaY > 0)', () => {
    state.zoom = 2;
    document.getElementById('zoom-viewport').dispatchEvent(
      new WheelEvent('wheel', {deltaY: 100, bubbles: true, cancelable: true}),
    );
    expect(state.zoom).toBeLessThan(2);
  });

  it('does not zoom below 1', () => {
    document.getElementById('zoom-viewport').dispatchEvent(
      new WheelEvent('wheel', {deltaY: 100, bubbles: true, cancelable: true}),
    );
    expect(state.zoom).toBe(1);
  });

  it('does not zoom above 10', () => {
    state.zoom = 9.9;
    for (let i = 0; i < 5; i++) {
      document.getElementById('zoom-viewport').dispatchEvent(
        new WheelEvent('wheel', {deltaY: -100, bubbles: true, cancelable: true}),
      );
    }
    expect(state.zoom).toBeLessThanOrEqual(10);
  });
});

// ── mousedown handler ─────────────────────────────────────

describe('mousedown handler', () => {
  it('does not start panning when zoom is 1', () => {
    document.getElementById('zoom-viewport').dispatchEvent(
      new MouseEvent('mousedown', {button: 0, bubbles: true, cancelable: true}),
    );
    expect(state.isPanning).toBe(false);
  });

  it('starts panning on left click when zoomed in', () => {
    state.zoom = 2;
    document.getElementById('zoom-viewport').dispatchEvent(
      new MouseEvent('mousedown', {button: 0, bubbles: true, cancelable: true}),
    );
    expect(state.isPanning).toBe(true);
    expect(document.getElementById('zoom-viewport').classList.contains('grabbing')).toBe(true);
  });

  it('ignores non-left-button clicks', () => {
    state.zoom = 2;
    document.getElementById('zoom-viewport').dispatchEvent(
      new MouseEvent('mousedown', {button: 2, bubbles: true, cancelable: true}),
    );
    expect(state.isPanning).toBe(false);
  });

  it('starts rect drawing on shift+click when currentPhotoId is set', () => {
    state.currentPhotoId = 5;
    document.getElementById('modal-img').getBoundingClientRect =
      () => ({left: 0, top: 0, width: 100, height: 100});
    document.getElementById('zoom-viewport').dispatchEvent(
      new MouseEvent('mousedown', {button: 0, shiftKey: true, bubbles: true, cancelable: true}),
    );
    expect(state.isDrawingRect).toBe(true);
    expect(document.getElementById('zoom-viewport').classList.contains('drawing')).toBe(true);
  });

  it('does not start rect drawing when currentPhotoId is null', () => {
    state.currentPhotoId = null;
    document.getElementById('zoom-viewport').dispatchEvent(
      new MouseEvent('mousedown', {button: 0, shiftKey: true, bubbles: true, cancelable: true}),
    );
    expect(state.isDrawingRect).toBe(false);
  });
});

// ── mousemove handler ─────────────────────────────────────

describe('mousemove handler', () => {
  beforeEach(() => {
    document.getElementById('modal-img').getBoundingClientRect =
      () => ({left: 0, top: 0, width: 100, height: 100});
  });

  it('sets wasDrag when panning moves more than 4px', () => {
    state.isPanning = true;
    state.zoom = 2;
    state.panStart = {x: 0, y: 0, panX: 0, panY: 0};
    document.dispatchEvent(new MouseEvent('mousemove', {clientX: 10, clientY: 10, bubbles: true}));
    expect(state.wasDrag).toBe(true);
  });

  it('does not set wasDrag for tiny pan (≤ 4px)', () => {
    state.isPanning = true;
    state.zoom = 2;
    state.panStart = {x: 0, y: 0, panX: 0, panY: 0};
    document.dispatchEvent(new MouseEvent('mousemove', {clientX: 2, clientY: 2, bubbles: true}));
    expect(state.wasDrag).toBe(false);
  });

  it('shows rect-preview during rect drawing', () => {
    state.isDrawingRect = true;
    state.currentRotation = 0;
    state.rectStart = {x: 0.1, y: 0.1};
    document.dispatchEvent(new MouseEvent('mousemove', {clientX: 40, clientY: 60, bubbles: true}));
    expect(document.getElementById('rect-preview').style.display).toBe('block');
  });

  it('positions rect-preview to span from rectStart to current cursor', () => {
    state.isDrawingRect = true;
    state.currentRotation = 0;
    state.rectStart = {x: 0.1, y: 0.1};
    document.dispatchEvent(new MouseEvent('mousemove', {clientX: 40, clientY: 60, bubbles: true}));
    const preview = document.getElementById('rect-preview');
    expect(parseFloat(preview.style.left)).toBeCloseTo(10, 5);
    expect(parseFloat(preview.style.top)).toBeCloseTo(10, 5);
    expect(parseFloat(preview.style.width)).toBeCloseTo(30, 5);
    expect(parseFloat(preview.style.height)).toBeCloseTo(50, 5);
  });
});

// ── mouseup handler ───────────────────────────────────────

describe('mouseup handler', () => {
  it('ends panning and removes grabbing class', () => {
    state.isPanning = true;
    document.getElementById('zoom-viewport').classList.add('grabbing');
    document.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
    expect(state.isPanning).toBe(false);
    expect(document.getElementById('zoom-viewport').classList.contains('grabbing')).toBe(false);
  });

  it('does nothing when neither panning nor drawing', () => {
    document.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
    expect(state.isPanning).toBe(false);
    expect(state.isDrawingRect).toBe(false);
  });

  it('clears rect drawing state and removes drawing class', () => {
    document.getElementById('modal-img').getBoundingClientRect =
      () => ({left: 0, top: 0, width: 100, height: 100});
    state.isDrawingRect = true;
    state.currentRotation = 0;
    state.rectStart = {x: 0.5, y: 0.5};
    document.getElementById('zoom-viewport').classList.add('drawing');
    // same-point mouseup → drag is zero, openCreateForm is not called
    document.dispatchEvent(new MouseEvent('mouseup', {clientX: 50, clientY: 50, bubbles: true}));
    expect(state.isDrawingRect).toBe(false);
    expect(state.rectStart).toBeNull();
    expect(document.getElementById('zoom-viewport').classList.contains('drawing')).toBe(false);
  });

  it('hides rect-preview on mouseup', () => {
    document.getElementById('modal-img').getBoundingClientRect =
      () => ({left: 0, top: 0, width: 100, height: 100});
    state.isDrawingRect = true;
    state.currentRotation = 0;
    state.rectStart = {x: 0.5, y: 0.5};
    document.getElementById('rect-preview').style.display = 'block';
    document.dispatchEvent(new MouseEvent('mouseup', {clientX: 50, clientY: 50, bubbles: true}));
    expect(document.getElementById('rect-preview').style.display).toBe('none');
  });
});
