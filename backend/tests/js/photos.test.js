import { vi, describe, it, expect, beforeAll, beforeEach, afterEach } from 'vitest';

vi.mock('@/api.js', () => ({
  getPhotos: vi.fn().mockResolvedValue([]),
  updatePhoto: vi.fn().mockResolvedValue({}),
}));

let loadPhotos, clearFilter, applyFilter, selectA, selectB, flickerAuto, stopAuto, flickerToggle, gridRotate;
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

  ({loadPhotos, clearFilter, applyFilter, selectA, selectB, flickerAuto, stopAuto, flickerToggle, gridRotate} =
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
  document.getElementById('flicker-view').classList.remove('visible');
  document.getElementById('img-a').style.transform = '';
  document.getElementById('img-b').style.transform = '';
  document.getElementById('flicker-img').style.transform = '';
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

// ── rotation in compare / flicker ─────────────────────────

const ROTATED_PHOTOS = [
  {id: 3, url: '/photos/c.jpg', filename: 'c.jpg', captured_at: '2026-01-03T10:00:00Z', rotation: 90,  growing_units: []},
  {id: 4, url: '/photos/d.jpg', filename: 'd.jpg', captured_at: '2026-01-04T10:00:00Z', rotation: 270, growing_units: []},
];

describe('compare slot rotation', () => {
  it('applies rotation transform to img-a when selecting a rotated photo', () => {
    state.allPhotos = ROTATED_PHOTOS;
    const e = {stopPropagation: vi.fn()};
    selectA(e, 0);
    expect(document.getElementById('img-a').style.transform).toBe('rotate(90deg)');
  });

  it('applies rotation transform to img-b when selecting a rotated photo', () => {
    state.allPhotos = ROTATED_PHOTOS;
    const e = {stopPropagation: vi.fn()};
    selectB(e, 1);
    expect(document.getElementById('img-b').style.transform).toBe('rotate(270deg)');
  });

  it('uses rotate(0deg) for a photo with rotation=0', () => {
    state.allPhotos = PHOTOS;
    const e = {stopPropagation: vi.fn()};
    selectA(e, 0);
    expect(document.getElementById('img-a').style.transform).toBe('rotate(0deg)');
  });

  it('uses rotate(0deg) for a photo with no rotation field', () => {
    const noRot = [{id: 5, url: '/photos/e.jpg', filename: 'e.jpg', captured_at: '2026-01-05T10:00:00Z', growing_units: []}];
    state.allPhotos = noRot;
    const e = {stopPropagation: vi.fn()};
    selectA(e, 0);
    expect(document.getElementById('img-a').style.transform).toBe('rotate(0deg)');
  });
});

describe('flicker frame rotation', () => {
  it('applies rotation of the shown photo to flicker-img', () => {
    state.photoA = ROTATED_PHOTOS[0]; // rotation 90
    state.photoB = ROTATED_PHOTOS[1]; // rotation 270
    flickerToggle(); // shows A
    expect(document.getElementById('flicker-img').style.transform).toBe('rotate(90deg)');
  });

  it('updates rotation when toggling to the other photo', () => {
    state.photoA = ROTATED_PHOTOS[0]; // rotation 90
    state.photoB = ROTATED_PHOTOS[1]; // rotation 270
    flickerToggle(); // shows A (90)
    flickerToggle(); // shows B (270)
    expect(document.getElementById('flicker-img').style.transform).toBe('rotate(270deg)');
  });
});

// ── gridRotate ────────────────────────────────────────────

describe('gridRotate', () => {
  let photo;

  beforeEach(async () => {
    photo = {id: 10, url: '/photos/x.jpg', filename: 'x.jpg', captured_at: '2026-01-01T10:00:00Z', rotation: 0, growing_units: []};
    state.allPhotos = [photo];
    // Inject a minimal photo card so gridRotate can update the DOM in-place
    document.getElementById('photo-grid').innerHTML =
      '<div class="photo-card" data-id="10"><img style=""></div>';
    const api = await import('@/api.js');
    vi.mocked(api.updatePhoto).mockResolvedValue({});
  });

  it('calls stopPropagation on the event', async () => {
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 10, 90);
    expect(e.stopPropagation).toHaveBeenCalled();
  });

  it('does nothing when photoId is not in allPhotos', async () => {
    const api = await import('@/api.js');
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 99, 90);
    expect(vi.mocked(api.updatePhoto)).not.toHaveBeenCalled();
  });

  it('applies the rotation delta and wraps at 360', async () => {
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 10, 90);
    expect(photo.rotation).toBe(90);
  });

  it('wraps backward rotation past 0 to 270', async () => {
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 10, -90);
    expect(photo.rotation).toBe(270);
  });

  it('updates the img transform in the grid card', async () => {
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 10, 90);
    const img = document.querySelector('.photo-card[data-id="10"] img');
    expect(img.style.transform).toBe('rotate(90deg)');
  });

  it('clears the img transform when rotation reaches 0', async () => {
    photo.rotation = 270;
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 10, 90);
    const img = document.querySelector('.photo-card[data-id="10"] img');
    expect(img.style.transform).toBe('');
  });

  it('calls updatePhoto with the new rotation', async () => {
    const api = await import('@/api.js');
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 10, 90);
    expect(vi.mocked(api.updatePhoto)).toHaveBeenCalledWith(10, {rotation: 90});
  });

  it('rolls back state.rotation on API failure', async () => {
    const api = await import('@/api.js');
    vi.mocked(api.updatePhoto).mockRejectedValueOnce(new Error('network'));
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 10, 90);
    expect(photo.rotation).toBe(0);
  });

  it('rolls back img transform on API failure', async () => {
    const api = await import('@/api.js');
    vi.mocked(api.updatePhoto).mockRejectedValueOnce(new Error('network'));
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 10, 90);
    const img = document.querySelector('.photo-card[data-id="10"] img');
    expect(img.style.transform).toBe('');
  });
});
