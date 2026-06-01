import { vi, describe, it, expect, beforeAll, beforeEach, afterEach } from 'vitest';

vi.mock('@/api.js', () => ({
  getPhotos: vi.fn().mockResolvedValue({photos: [], total: 0}),
  updatePhoto: vi.fn().mockResolvedValue({}),
  deletePhoto: vi.fn().mockResolvedValue(undefined),
  batchUpdatePhotos: vi.fn().mockResolvedValue([]),
}));

let loadPhotos, clearFilter, applyFilter, selectA, selectB, flickerAuto, stopAuto, flickerToggle, gridRotate, gridDelete, readFiltersFromHash, toggleSelectMode, selectAll, deleteSelected, downloadSelected;
let batchSetType, batchSetLocation, batchAddUnit, batchAddLabel;
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
    <!-- select mode -->
    <button id="select-mode-btn"></button>
    <div id="select-bar" class="hidden">
      <span id="select-count"></span>
      <button id="delete-selected-btn" disabled></button>
      <button id="download-selected-btn" disabled></button>
      <button id="copy-sheet-btn" disabled></button>
      <select id="batch-type-select" disabled><option value="">Set type…</option><option value="overview">Overview</option><option value="__none__">— clear —</option></select>
      <select id="batch-location-select" disabled><option value="">Set location…</option><option value="5">Balcony</option><option value="__none__">— clear —</option></select>
      <select id="batch-unit-select" disabled><option value="">+ Unit…</option><option value="7">Basil</option></select>
      <select id="batch-label-select" disabled><option value="">+ Label…</option><option value="9">aphids</option></select>
    </div>
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

  ({loadPhotos, clearFilter, applyFilter, selectA, selectB, flickerAuto, stopAuto, flickerToggle, gridRotate, gridDelete, readFiltersFromHash, toggleSelectMode, selectAll, deleteSelected, downloadSelected, batchSetType, batchSetLocation, batchAddUnit, batchAddLabel} =
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
  vi.mocked(api.getPhotos).mockResolvedValue({photos: [], total: 0});
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
    getPhotos.mockResolvedValueOnce({photos: PHOTOS, total: PHOTOS.length});
    await loadPhotos();
    expect(state.allPhotos).toEqual(PHOTOS);
  });
});

// ── renderGrid ────────────────────────────────────────────

describe('renderGrid (via loadPhotos)', () => {
  it('points the grid img at the oriented url and uses no css transform', async () => {
    const {getPhotos} = await import('@/api.js');
    getPhotos.mockResolvedValueOnce({
      photos: [{id: 7, url: '/photos/g.jpg', filename: 'g.jpg', captured_at: '2026-01-01T10:00:00Z', rotation: 90, growing_units: []}],
      total: 1,
    });
    await loadPhotos();
    const img = document.querySelector('#photo-grid .photo-card[data-id="7"] img');
    expect(img.getAttribute('src')).toBe('/photos/g.jpg?oriented=1&v=90');
    expect(img.style.transform).toBe('');
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

// ── readFiltersFromHash ───────────────────────────────────

describe('readFiltersFromHash', () => {
  afterEach(() => {
    history.replaceState(null, '', window.location.pathname);
  });

  it('restores date range and source from hash', () => {
    history.replaceState(null, '', '#start=2099-01-01&end=2099-12-31&source=pi');
    readFiltersFromHash();
    expect(document.getElementById('start').value).toBe('2099-01-01');
    expect(document.getElementById('end').value).toBe('2099-12-31');
    expect(document.getElementById('filter-source').value).toBe('pi');
  });

  it('restores unit and label chip state from hash, reflected in next loadPhotos call', async () => {
    history.replaceState(null, '', '#unit=3&label=5');
    readFiltersFromHash();
    const api = await import('@/api.js');
    await loadPhotos();
    const call = vi.mocked(api.getPhotos).mock.calls.at(-1)[0];
    expect(call.unit).toBe('3');
    expect(call.label).toBe('5');
  });

  it('restores combined hash: tab param is ignored by readFiltersFromHash, filters and chips all active', async () => {
    history.replaceState(null, '', '#tab=gallery&start=2099-01-01&unit=3&label=5');
    readFiltersFromHash();
    // date filter is applied directly to the DOM element
    expect(document.getElementById('start').value).toBe('2099-01-01');
    // unit and label chip state flows into the next loadPhotos call
    const api = await import('@/api.js');
    await loadPhotos();
    const call = vi.mocked(api.getPhotos).mock.calls.at(-1)[0];
    expect(call.unit).toBe('3');
    expect(call.label).toBe('5');
    // tab= is not readFiltersFromHash's concern — switchTab in app.js handles it
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

  it('points the grid img at the oriented url with the new rotation', async () => {
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 10, 90);
    const img = document.querySelector('.photo-card[data-id="10"] img');
    expect(img.getAttribute('src')).toBe('/photos/x.jpg?oriented=1&v=90');
  });

  it('uses v=0 in the oriented url when rotation reaches 0', async () => {
    photo.rotation = 270;
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 10, 90);
    const img = document.querySelector('.photo-card[data-id="10"] img');
    expect(img.getAttribute('src')).toBe('/photos/x.jpg?oriented=1&v=0');
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

  it('rolls back the img src on API failure', async () => {
    const api = await import('@/api.js');
    vi.mocked(api.updatePhoto).mockRejectedValueOnce(new Error('network'));
    const e = {stopPropagation: vi.fn()};
    await gridRotate(e, 10, 90);
    const img = document.querySelector('.photo-card[data-id="10"] img');
    expect(img.getAttribute('src')).toBe('/photos/x.jpg?oriented=1&v=0');
  });
});

// ── gridDelete ────────────────────────────────────────────

describe('gridDelete', () => {
  let photo;

  beforeEach(async () => {
    photo = {id: 20, url: '/photos/del.jpg', filename: 'del.jpg', captured_at: '2026-01-01T10:00:00Z', rotation: 0, growing_units: []};
    state.allPhotos = [photo];
    state.totalPhotos = 1;
    state.photoA = null;
    state.photoB = null;
    document.getElementById('photo-grid').innerHTML =
      '<div class="photo-card" data-id="20"><img src=""></div>';
    const api = await import('@/api.js');
    vi.mocked(api.deletePhoto).mockResolvedValue(undefined);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls stopPropagation', async () => {
    const e = {stopPropagation: vi.fn()};
    await gridDelete(e, 20);
    expect(e.stopPropagation).toHaveBeenCalled();
  });

  it('calls deletePhoto with the photo id', async () => {
    const api = await import('@/api.js');
    const e = {stopPropagation: vi.fn()};
    await gridDelete(e, 20);
    expect(vi.mocked(api.deletePhoto)).toHaveBeenCalledWith(20);
  });

  it('removes photo from state.allPhotos', async () => {
    const e = {stopPropagation: vi.fn()};
    await gridDelete(e, 20);
    expect(state.allPhotos.find(p => p.id === 20)).toBeUndefined();
  });

  it('decrements state.totalPhotos', async () => {
    const e = {stopPropagation: vi.fn()};
    await gridDelete(e, 20);
    expect(state.totalPhotos).toBe(0);
  });

  it('does not call deletePhoto when confirm is cancelled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const api = await import('@/api.js');
    const e = {stopPropagation: vi.fn()};
    await gridDelete(e, 20);
    expect(vi.mocked(api.deletePhoto)).not.toHaveBeenCalled();
  });

  it('clears state.photoA when it matches the deleted photo', async () => {
    state.photoA = photo;
    const e = {stopPropagation: vi.fn()};
    await gridDelete(e, 20);
    expect(state.photoA).toBeNull();
  });

  it('clears state.photoB when it matches the deleted photo', async () => {
    state.photoB = photo;
    const e = {stopPropagation: vi.fn()};
    await gridDelete(e, 20);
    expect(state.photoB).toBeNull();
  });

  it('leaves state.photoA intact when it does not match the deleted photo', async () => {
    const other = {id: 99, url: '/photos/other.jpg', filename: 'other.jpg', captured_at: '2026-01-01T10:00:00Z', rotation: 0, growing_units: []};
    state.photoA = other;
    const e = {stopPropagation: vi.fn()};
    await gridDelete(e, 20);
    expect(state.photoA).toBe(other);
  });
});

// ── select-mode helpers ───────────────────────────────────

// Ensures select mode is off and all card selections cleared before/after
// each select-mode test, regardless of what the test did.
function resetSelectMode() {
  // toggleSelectMode() clears selectedIds AND removes .selected from cards.
  // Only call when in select mode; if already off, module state is already clean
  // (selectedIds can only be populated while selectMode is true).
  if (document.getElementById('photo-grid').classList.contains('select-mode')) {
    toggleSelectMode();
  }
}

// ── toggleSelectMode ──────────────────────────────────────

describe('toggleSelectMode', () => {
  afterEach(resetSelectMode);

  it('adds select-mode class to grid and removes hidden from select-bar', () => {
    toggleSelectMode();
    expect(document.getElementById('photo-grid').classList.contains('select-mode')).toBe(true);
    expect(document.getElementById('select-bar').classList.contains('hidden')).toBe(false);
  });

  it('removes select-mode class when called a second time', () => {
    toggleSelectMode();
    toggleSelectMode();
    expect(document.getElementById('photo-grid').classList.contains('select-mode')).toBe(false);
    expect(document.getElementById('select-bar').classList.contains('hidden')).toBe(true);
  });

  it('clears existing selections when toggling off', async () => {
    const api = await import('@/api.js');
    vi.mocked(api.getPhotos).mockResolvedValueOnce({photos: PHOTOS, total: PHOTOS.length});
    await loadPhotos();
    toggleSelectMode();
    // simulate selecting a card
    const card = document.querySelector('.photo-card[data-id="1"]');
    card.classList.add('selected');
    toggleSelectMode(); // off
    expect(document.querySelectorAll('.photo-card.selected')).toHaveLength(0);
  });
});

// ── selectAll ─────────────────────────────────────────────

describe('selectAll', () => {
  beforeEach(async () => {
    resetSelectMode();
    const api = await import('@/api.js');
    vi.mocked(api.getPhotos).mockResolvedValueOnce({photos: PHOTOS, total: PHOTOS.length});
    await loadPhotos();
    toggleSelectMode();
  });

  afterEach(resetSelectMode);

  it('adds selected class to every card', () => {
    selectAll();
    expect(document.querySelectorAll('.photo-card.selected')).toHaveLength(PHOTOS.length);
  });

  it('updates the count in the select bar', () => {
    selectAll();
    expect(document.getElementById('select-count').textContent).toBe(`${PHOTOS.length} selected`);
  });

  it('enables the action buttons', () => {
    selectAll();
    expect(document.getElementById('delete-selected-btn').disabled).toBe(false);
    expect(document.getElementById('download-selected-btn').disabled).toBe(false);
  });

  it('does nothing when not in select mode', () => {
    toggleSelectMode(); // back off
    selectAll();
    expect(document.querySelectorAll('.photo-card.selected')).toHaveLength(0);
  });
});

// ── deleteSelected ────────────────────────────────────────

describe('deleteSelected', () => {
  beforeEach(async () => {
    resetSelectMode();
    const api = await import('@/api.js');
    vi.mocked(api.getPhotos).mockResolvedValueOnce({photos: PHOTOS, total: PHOTOS.length});
    await loadPhotos();
    state.totalPhotos = PHOTOS.length;
    toggleSelectMode();
    selectAll();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.deletePhoto).mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    resetSelectMode();
  });

  it('removes deleted photos from state.allPhotos', async () => {
    await deleteSelected();
    expect(state.allPhotos).toHaveLength(0);
  });

  it('exits select mode after deletion', async () => {
    await deleteSelected();
    expect(document.getElementById('photo-grid').classList.contains('select-mode')).toBe(false);
  });

  it('does nothing when confirm is cancelled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const api = await import('@/api.js');
    await deleteSelected();
    expect(vi.mocked(api.deletePhoto)).not.toHaveBeenCalled();
  });
});

// ── downloadSelected ──────────────────────────────────────

describe('downloadSelected', () => {
  beforeEach(async () => {
    resetSelectMode();
    const api = await import('@/api.js');
    vi.mocked(api.getPhotos).mockResolvedValueOnce({photos: PHOTOS, total: PHOTOS.length});
    await loadPhotos();
    toggleSelectMode();
    selectAll();
  });

  afterEach(resetSelectMode);

  it('creates an anchor pointing at /photos/export with all selected ids', () => {
    const clicks = [];
    const origCreate = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation(tag => {
      const el = origCreate(tag);
      if (tag === 'a') vi.spyOn(el, 'click').mockImplementation(() => clicks.push(el));
      return el;
    });
    downloadSelected();
    expect(clicks).toHaveLength(1);
    const ids = PHOTOS.map(p => p.id).sort((a, b) => a - b).join(',');
    expect(clicks[0].href).toContain(`/photos/export?ids=`);
    expect(clicks[0].href).toContain(`ids=${ids}`);
    expect(clicks[0].download).toBe('photos.zip');
    vi.restoreAllMocks();
  });

  it('does nothing when nothing is selected', () => {
    toggleSelectMode(); // clears selection
    toggleSelectMode(); // back on
    const clicks = [];
    const origCreate = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation(tag => {
      const el = origCreate(tag);
      if (tag === 'a') vi.spyOn(el, 'click').mockImplementation(() => clicks.push(el));
      return el;
    });
    downloadSelected();
    expect(clicks).toHaveLength(0);
    vi.restoreAllMocks();
  });
});

// ── drag-to-select ────────────────────────────────────────

describe('drag-to-select', () => {
  beforeEach(async () => {
    resetSelectMode();
    document.dispatchEvent(new MouseEvent('mouseup')); // terminate any active drag-selection state
    const api = await import('@/api.js');
    vi.mocked(api.getPhotos).mockResolvedValueOnce({photos: PHOTOS, total: PHOTOS.length});
    await loadPhotos();
    toggleSelectMode();
  });

  afterEach(() => {
    document.dispatchEvent(new MouseEvent('mouseup'));
    resetSelectMode();
  });

  function mousedown(card) {
    card.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
  }
  function mouseover(card) {
    card.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
  }

  it('mousedown on a card selects it', () => {
    const card = document.querySelector('.photo-card[data-id="1"]');
    mousedown(card);
    expect(card.classList.contains('selected')).toBe(true);
  });

  it('subsequent click after mousedown does not double-toggle', () => {
    const card = document.querySelector('.photo-card[data-id="1"]');
    mousedown(card);
    card.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
    expect(card.classList.contains('selected')).toBe(true);
  });

  it('mouseover while holding adds the hovered card', () => {
    const card1 = document.querySelector('.photo-card[data-id="1"]');
    const card2 = document.querySelector('.photo-card[data-id="2"]');
    mousedown(card1);
    mouseover(card2);
    expect(card2.classList.contains('selected')).toBe(true);
  });

  it('dragging over an already-selected card deselects it', () => {
    const card1 = document.querySelector('.photo-card[data-id="1"]');
    const card2 = document.querySelector('.photo-card[data-id="2"]');
    // pre-select card2
    mousedown(card2);
    document.dispatchEvent(new MouseEvent('mouseup'));
    // now drag-deselect by starting on card2
    mousedown(card2);
    mouseover(card1);
    expect(card2.classList.contains('selected')).toBe(false);
    expect(card1.classList.contains('selected')).toBe(false);
  });

  it('mouseup stops drag — further mouseover has no effect', () => {
    const card1 = document.querySelector('.photo-card[data-id="1"]');
    const card2 = document.querySelector('.photo-card[data-id="2"]');
    mousedown(card1);
    document.dispatchEvent(new MouseEvent('mouseup'));
    mouseover(card2);
    expect(card2.classList.contains('selected')).toBe(false);
  });
});

// ── batch classify (set type/location, add unit/label) ────

describe('batch classify', () => {
  let api;
  beforeEach(async () => {
    resetSelectMode();
    api = await import('@/api.js');
    vi.mocked(api.getPhotos).mockResolvedValueOnce({photos: PHOTOS, total: PHOTOS.length});
    await loadPhotos();
    toggleSelectMode();
    selectAll();
    vi.mocked(api.batchUpdatePhotos).mockResolvedValue(
      PHOTOS.map(p => ({...p, photo_type: 'overview'}))
    );
  });

  afterEach(() => {
    vi.mocked(api.batchUpdatePhotos).mockReset();
    resetSelectMode();
  });

  it('batchSetType posts the selected ids with the chosen photo_type', async () => {
    const sel = document.getElementById('batch-type-select');
    sel.value = 'overview';
    await batchSetType(sel);
    expect(vi.mocked(api.batchUpdatePhotos)).toHaveBeenCalledWith({
      ids: PHOTOS.map(p => p.id),
      photo_type: 'overview',
    });
  });

  it('batchSetType with the clear sentinel sends null', async () => {
    const sel = document.getElementById('batch-type-select');
    sel.value = '__none__';
    await batchSetType(sel);
    expect(vi.mocked(api.batchUpdatePhotos)).toHaveBeenCalledWith({
      ids: PHOTOS.map(p => p.id),
      photo_type: null,
    });
  });

  it('batchSetLocation parses the id and clear sends null', async () => {
    const sel = document.getElementById('batch-location-select');
    sel.value = '5';
    await batchSetLocation(sel);
    expect(vi.mocked(api.batchUpdatePhotos)).toHaveBeenCalledWith({
      ids: PHOTOS.map(p => p.id),
      location_id: 5,
    });
    sel.value = '__none__';
    await batchSetLocation(sel);
    expect(vi.mocked(api.batchUpdatePhotos)).toHaveBeenLastCalledWith({
      ids: PHOTOS.map(p => p.id),
      location_id: null,
    });
  });

  it('batchAddUnit posts add_unit_ids', async () => {
    const sel = document.getElementById('batch-unit-select');
    sel.value = '7';
    await batchAddUnit(sel);
    expect(vi.mocked(api.batchUpdatePhotos)).toHaveBeenCalledWith({
      ids: PHOTOS.map(p => p.id),
      add_unit_ids: [7],
    });
  });

  it('batchAddLabel posts add_label_ids', async () => {
    const sel = document.getElementById('batch-label-select');
    sel.value = '9';
    await batchAddLabel(sel);
    expect(vi.mocked(api.batchUpdatePhotos)).toHaveBeenCalledWith({
      ids: PHOTOS.map(p => p.id),
      add_label_ids: [9],
    });
  });

  it('splices the returned photos back into state.allPhotos', async () => {
    const sel = document.getElementById('batch-type-select');
    sel.value = 'overview';
    await batchSetType(sel);
    expect(state.allPhotos.every(p => p.photo_type === 'overview')).toBe(true);
  });

  it('resets the control and preserves the selection for chained actions', async () => {
    const sel = document.getElementById('batch-type-select');
    sel.value = 'overview';
    await batchSetType(sel);
    expect(sel.value).toBe('');
    // selection survived — a follow-up action still targets both photos
    sel.value = 'overview';
    await batchSetType(sel);
    expect(vi.mocked(api.batchUpdatePhotos)).toHaveBeenLastCalledWith({
      ids: PHOTOS.map(p => p.id),
      photo_type: 'overview',
    });
  });

  it('does nothing on the placeholder option', async () => {
    const sel = document.getElementById('batch-type-select');
    sel.value = '';
    await batchSetType(sel);
    expect(vi.mocked(api.batchUpdatePhotos)).not.toHaveBeenCalled();
  });

  it('does nothing when nothing is selected', async () => {
    toggleSelectMode(); // off — clears selection
    toggleSelectMode(); // on, empty
    const sel = document.getElementById('batch-type-select');
    sel.value = 'overview';
    await batchSetType(sel);
    expect(vi.mocked(api.batchUpdatePhotos)).not.toHaveBeenCalled();
    expect(sel.value).toBe('');
  });
});
