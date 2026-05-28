import { vi, describe, it, expect, beforeAll, beforeEach, afterEach } from 'vitest';

vi.mock('@/api.js', () => ({
  getPhotos: vi.fn().mockResolvedValue([]),
}));

let loadPhotos, clearFilter, applyFilter, selectA, selectB, flickerAuto, stopAuto, flickerToggle;
let state;

const PHOTOS = [
  {id: 1, url: '/photos/a.jpg', filename: 'a.jpg', captured_at: '2026-01-01T10:00:00Z', rotation: 0, growing_units: []},
  {id: 2, url: '/photos/b.jpg', filename: 'b.jpg', captured_at: '2026-01-02T10:00:00Z', rotation: 0, growing_units: []},
];

beforeAll(async () => {
  // Set up ALL DOM elements needed by photos.js and timelapse.js at module load time
  // before the dynamic import so top-level code can run.
  document.body.innerHTML = `
    <div id="status"></div>
    <!-- filter inputs -->
    <input id="start" value="">
    <input id="end" value="">
    <select id="filter-source"><option value="">All</option></select>
    <select id="filter-photo-type"><option value="">All</option></select>
    <select id="filter-location"><option value="">All</option></select>
    <select id="filter-unit"><option value="">All</option></select>
    <!-- photo grid -->
    <div id="photo-grid"></div>
    <!-- compare/flicker -->
    <div id="slot-a-empty"></div>
    <img id="img-a" style="display:none" src="">
    <div id="cap-a"></div>
    <div id="slot-b-empty"></div>
    <img id="img-b" style="display:none" src="">
    <div id="cap-b"></div>
    <button id="btn-toggle" disabled></button>
    <button id="btn-auto" disabled>Auto flicker</button>
    <div id="flicker-view"><img id="flicker-img" src=""><span id="flicker-label"></span></div>
    <input id="flicker-speed" type="range" value="4">
    <span id="flicker-fps"></span>
    <!-- timelapse (needed because photos.js imports timelapse.js) -->
    <div id="tl-empty" style="display:none"></div>
    <img id="tl-img" style="display:none" src="">
    <div id="tl-label" style="display:none"></div>
    <span id="tl-counter"></span>
    <button id="tl-prev" disabled></button>
    <button id="tl-play" disabled>&#9654; Play</button>
    <button id="tl-next" disabled></button>
    <input id="tl-speed" type="range" value="2">
    <span id="tl-fps"></span>
  `;

  ({loadPhotos, clearFilter, applyFilter, selectA, selectB, flickerAuto, stopAuto, flickerToggle} =
    await import('@/photos.js'));
  ({state} = await import('@/state.js'));
});

beforeEach(async () => {
  state.allPhotos = [];
  state.photoA = null;
  state.photoB = null;
  state.flickerTimer = null;
  state.flickerShowing = 'a';
  vi.clearAllMocks();
  const api = await import('@/api.js');
  vi.mocked(api.getPhotos).mockResolvedValue([]);
  document.getElementById('start').value = '';
  document.getElementById('end').value = '';
  document.getElementById('filter-source').value = '';
  document.getElementById('filter-photo-type').value = '';
  document.getElementById('filter-location').value = '';
  document.getElementById('filter-unit').value = '';
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  if (state.flickerTimer) { clearInterval(state.flickerTimer); state.flickerTimer = null; }
});

// ── loadPhotos ────────────────────────────────────────────

describe('loadPhotos', () => {
  it('calls getPhotos with no params when filters are empty', async () => {
    const {getPhotos} = await import('@/api.js');
    await loadPhotos();
    expect(getPhotos).toHaveBeenCalledWith(expect.objectContaining({
      source: '', ptype: '', location: '', unit: '',
    }));
  });

  it('passes filter values to getPhotos', async () => {
    const {getPhotos} = await import('@/api.js');
    document.getElementById('filter-source').innerHTML = '<option value="">All</option><option value="pi">Pi</option>';
    document.getElementById('filter-source').value = 'pi';
    document.getElementById('filter-photo-type').innerHTML = '<option value="">All</option><option value="overview">Overview</option>';
    document.getElementById('filter-photo-type').value = 'overview';
    await loadPhotos();
    const call = getPhotos.mock.calls[0][0];
    expect(call.source).toBe('pi');
    expect(call.ptype).toBe('overview');
  });

  it('sets state.allPhotos from the api response', async () => {
    const {getPhotos} = await import('@/api.js');
    getPhotos.mockResolvedValueOnce(PHOTOS);
    await loadPhotos();
    expect(state.allPhotos).toEqual(PHOTOS);
  });
});

// ── clearFilter ───────────────────────────────────────────

describe('clearFilter', () => {
  it('resets all filter input values to empty', async () => {
    document.getElementById('start').value = '2026-01-01';
    document.getElementById('end').value = '2026-01-31';
    document.getElementById('filter-source').innerHTML =
      '<option value="">All</option><option value="pi">Pi</option>';
    document.getElementById('filter-source').value = 'pi';
    await clearFilter();
    expect(document.getElementById('start').value).toBe('');
    expect(document.getElementById('end').value).toBe('');
    expect(document.getElementById('filter-source').value).toBe('');
  });
});

// ── selectA / selectB ─────────────────────────────────────

describe('selectA', () => {
  it('sets state.photoA to allPhotos[idx]', () => {
    state.allPhotos = PHOTOS;
    const e = {stopPropagation: vi.fn()};
    selectA(e, 1);
    expect(state.photoA).toBe(PHOTOS[1]);
  });

  it('calls stopPropagation', () => {
    state.allPhotos = PHOTOS;
    const e = {stopPropagation: vi.fn()};
    selectA(e, 0);
    expect(e.stopPropagation).toHaveBeenCalled();
  });
});

describe('selectB', () => {
  it('sets state.photoB to allPhotos[idx]', () => {
    state.allPhotos = PHOTOS;
    const e = {stopPropagation: vi.fn()};
    selectB(e, 0);
    expect(state.photoB).toBe(PHOTOS[0]);
  });
});

// ── flickerAuto / stopAuto ────────────────────────────────

describe('flickerAuto', () => {
  it('starts the flicker timer', () => {
    state.photoA = PHOTOS[0];
    state.photoB = PHOTOS[1];
    flickerAuto();
    expect(state.flickerTimer).not.toBeNull();
  });

  it('calling a second time stops the timer', () => {
    state.photoA = PHOTOS[0];
    state.photoB = PHOTOS[1];
    flickerAuto();
    flickerAuto();
    expect(state.flickerTimer).toBeNull();
  });
});

describe('stopAuto', () => {
  it('clears the timer', () => {
    state.photoA = PHOTOS[0];
    state.photoB = PHOTOS[1];
    flickerAuto();
    stopAuto();
    expect(state.flickerTimer).toBeNull();
  });

  it('resets btn-auto text', () => {
    stopAuto();
    expect(document.getElementById('btn-auto').textContent).toBe('Auto flicker');
  });
});
