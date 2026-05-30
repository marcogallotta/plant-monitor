import { vi, describe, it, expect, beforeAll, beforeEach } from 'vitest';

const mockFn = () => vi.fn().mockResolvedValue(undefined);

vi.mock('@/api.js', () => ({
  getLocations: vi.fn().mockResolvedValue([]),
  getGrowingUnits: vi.fn().mockResolvedValue([]),
  getLabels: vi.fn().mockResolvedValue([]),
}));

vi.mock('@/utils.js', () => ({ populateSelect: vi.fn() }));

vi.mock('@/photos.js', () => ({
  loadPhotos: mockFn(),
  applyFilter: vi.fn(), clearFilter: vi.fn(), loadMorePhotos: vi.fn(),
  selectA: vi.fn(), selectB: vi.fn(),
  flickerToggle: vi.fn(), flickerAuto: vi.fn(), stopAuto: vi.fn(), gridRotate: vi.fn(), gridDelete: vi.fn(),
  renderQuickChips: vi.fn(),
  readFiltersFromHash: vi.fn(),
}));

vi.mock('@/modal.js', () => ({
  openModal: vi.fn(), closeModal: vi.fn(), showModalPhoto: vi.fn(),
  rotatePhoto: vi.fn(), identityUpdate: mockFn(),
  toggleModalLogEvent: vi.fn(), logModalEvent: mockFn(),
}));

vi.mock('@/notes.js', () => ({
  initNotes: vi.fn(),
  modalImgClick: vi.fn(), noteSave: mockFn(), noteDelete: mockFn(), noteCancel: vi.fn(),
}));

vi.mock('@/labels.js', () => ({
  handleLabelInput: vi.fn(), handleLabelKeydown: mockFn(),
}));

vi.mock('@/timelapse.js', () => ({
  tlPrev: vi.fn(), tlPlayPause: vi.fn(), tlNext: vi.fn(),
}));

vi.mock('@/upload.js', () => ({
  initUpload: vi.fn(),
  submitManualUpload: mockFn(),
}));

vi.mock('@/zoom.js', () => ({ visualToStored: vi.fn() }));

vi.mock('@/events.js', () => ({
  initEvents: vi.fn(),
  createLocation: mockFn(), createUnit: mockFn(),
  logEvent: mockFn(),
}));

vi.mock('@/sdImport.js', () => ({
  initSdImport: vi.fn(),
  handleSdFolderInput: vi.fn(), handleSdScan: vi.fn(),
  sdAddGroup: vi.fn(), sdAddMore: vi.fn(),
  sdSelectAllVisible: vi.fn(), sdDeselectAll: vi.fn(),
  sdLoadMore: vi.fn(), sdUploadSelected: mockFn(),
}));

beforeAll(async () => {
  localStorage.clear();
  document.body.innerHTML = `
    <div id="modal" class="hidden"></div>
    <div class="tab-content" id="tab-gallery"></div>
    <div class="tab-content" id="tab-import"></div>
    <div class="tab-content" id="tab-events"></div>
    <div class="tab-content" id="tab-manage"></div>
    <button class="tab-btn" data-tab="gallery"></button>
    <button class="tab-btn" data-tab="import"></button>
    <button class="tab-btn" data-tab="events"></button>
    <button class="tab-btn" data-tab="manage"></button>
  `;
  await import('@/app.js');
});

// ── window exports ────────────────────────────────────────

describe('window exports', () => {
  const expected = [
    'applyFilter', 'clearFilter', 'loadMorePhotos',
    'openModal', 'closeModal', 'modalImgClick',
    'modalPrev', 'modalNext',
    'selectA', 'selectB',
    'rotatePhoto',
    'handleLabelInput', 'handleLabelKeydown',
    'flickerToggle', 'flickerAuto', 'gridRotate', 'gridDelete',
    'tlPrev', 'tlPlayPause', 'tlNext',
    'noteSave', 'noteDelete', 'noteCancel',
    'submitManualUpload',
    'sdSelectAllVisible', 'sdDeselectAll', 'sdLoadMore', 'sdUploadSelected',
    'createLocation', 'createUnit',
    'logEvent',
    'handleSdFolderInput', 'handleSdScan', 'sdAddGroup', 'sdAddMore',
    'identityUpdate',
    'toggleModalLogEvent', 'logModalEvent',
    'switchTab',
  ];

  for (const name of expected) {
    it(`exposes ${name} on window`, () => {
      expect(typeof window[name]).toBe('function');
    });
  }
});

// ── switchTab ─────────────────────────────────────────────

describe('switchTab', () => {
  it('defaults to gallery on boot', () => {
    expect(document.getElementById('tab-gallery').classList.contains('active')).toBe(true);
  });

  it('shows the target tab and hides others', () => {
    window.switchTab('import');
    expect(document.getElementById('tab-import').classList.contains('active')).toBe(true);
    expect(document.getElementById('tab-gallery').classList.contains('active')).toBe(false);
    window.switchTab('gallery');
  });

  it('marks the matching tab button active', () => {
    window.switchTab('events');
    const btn = document.querySelector('.tab-btn[data-tab="events"]');
    expect(btn.classList.contains('active')).toBe(true);
    window.switchTab('gallery');
  });

  it('falls back to gallery for an unknown tab name', () => {
    window.switchTab('nonexistent');
    expect(document.getElementById('tab-gallery').classList.contains('active')).toBe(true);
  });

  it('persists active tab to the URL hash', () => {
    window.switchTab('manage');
    expect(new URLSearchParams(window.location.hash.slice(1)).get('tab')).toBe('manage');
    window.switchTab('gallery');
  });
});

// ── keydown handler ───────────────────────────────────────

describe('keydown handler', () => {
  let modal, closeModal, stopAuto, showModalPhoto, flickerToggle;

  beforeAll(async () => {
    modal = document.getElementById('modal');
    ({ closeModal, showModalPhoto } = await import('@/modal.js'));
    ({ stopAuto, flickerToggle } = await import('@/photos.js'));
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  function fire(key) {
    document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
  }

  it('Escape calls closeModal and stopAuto', () => {
    fire('Escape');
    expect(closeModal).toHaveBeenCalled();
    expect(stopAuto).toHaveBeenCalled();
  });

  it('f calls flickerToggle', () => {
    fire('f');
    expect(flickerToggle).toHaveBeenCalled();
  });

  it('F calls flickerToggle', () => {
    fire('F');
    expect(flickerToggle).toHaveBeenCalled();
  });

  it('ArrowRight calls showModalPhoto when modal is open and not at end', async () => {
    const { state } = await import('@/state.js');
    state.allPhotos = [{}, {}, {}];
    state.currentIndex = 0;
    modal.classList.remove('hidden');
    fire('ArrowRight');
    expect(showModalPhoto).toHaveBeenCalledWith(1);
    modal.classList.add('hidden');
  });

  it('ArrowRight does nothing when at last photo', async () => {
    const { state } = await import('@/state.js');
    state.allPhotos = [{}, {}];
    state.currentIndex = 1;
    modal.classList.remove('hidden');
    fire('ArrowRight');
    expect(showModalPhoto).not.toHaveBeenCalled();
    modal.classList.add('hidden');
  });

  it('ArrowLeft calls showModalPhoto when modal is open and not at start', async () => {
    const { state } = await import('@/state.js');
    state.allPhotos = [{}, {}, {}];
    state.currentIndex = 2;
    modal.classList.remove('hidden');
    fire('ArrowLeft');
    expect(showModalPhoto).toHaveBeenCalledWith(1);
    modal.classList.add('hidden');
  });

  it('ArrowLeft does nothing when at first photo', async () => {
    const { state } = await import('@/state.js');
    state.allPhotos = [{}, {}];
    state.currentIndex = 0;
    modal.classList.remove('hidden');
    fire('ArrowLeft');
    expect(showModalPhoto).not.toHaveBeenCalled();
    modal.classList.add('hidden');
  });

  it('ArrowRight does nothing when modal is closed', async () => {
    const { state } = await import('@/state.js');
    state.allPhotos = [{}, {}];
    state.currentIndex = 0;
    modal.classList.add('hidden');
    fire('ArrowRight');
    expect(showModalPhoto).not.toHaveBeenCalled();
  });
});
