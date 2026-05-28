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
  applyFilter: vi.fn(), clearFilter: vi.fn(),
  selectA: vi.fn(), selectB: vi.fn(),
  flickerToggle: vi.fn(), flickerAuto: vi.fn(), stopAuto: vi.fn(), gridRotate: vi.fn(),
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
  toggleUploadPanel: vi.fn(), submitManualUpload: mockFn(),
}));

vi.mock('@/zoom.js', () => ({ visualToStored: vi.fn() }));

vi.mock('@/events.js', () => ({
  initEvents: vi.fn(),
  toggleManagePanel: vi.fn(), createLocation: mockFn(), createUnit: mockFn(),
  toggleEventsPanel: vi.fn(), logEvent: mockFn(),
}));

vi.mock('@/sdImport.js', () => ({
  initSdImport: vi.fn(),
  toggleSdPanel: vi.fn(), handleSdFolderInput: vi.fn(), handleSdScan: vi.fn(),
  sdAddGroup: vi.fn(), sdAddMore: vi.fn(),
  sdSelectAllVisible: vi.fn(), sdDeselectAll: vi.fn(),
  sdLoadMore: vi.fn(), sdUploadSelected: mockFn(),
}));

beforeAll(async () => {
  document.body.innerHTML = `<div id="modal" class="hidden"></div>`;
  await import('@/app.js');
});

// ── window exports ────────────────────────────────────────

describe('window exports', () => {
  const expected = [
    'applyFilter', 'clearFilter',
    'openModal', 'closeModal', 'modalImgClick',
    'modalPrev', 'modalNext',
    'selectA', 'selectB',
    'rotatePhoto',
    'handleLabelInput', 'handleLabelKeydown',
    'flickerToggle', 'flickerAuto', 'gridRotate',
    'tlPrev', 'tlPlayPause', 'tlNext',
    'noteSave', 'noteDelete', 'noteCancel',
    'toggleUploadPanel', 'submitManualUpload',
    'toggleSdPanel', 'sdSelectAllVisible', 'sdDeselectAll', 'sdLoadMore', 'sdUploadSelected',
    'toggleManagePanel', 'createLocation', 'createUnit',
    'toggleEventsPanel', 'logEvent',
    'handleSdFolderInput', 'handleSdScan', 'sdAddGroup', 'sdAddMore',
    'identityUpdate',
    'toggleModalLogEvent', 'logModalEvent',
  ];

  for (const name of expected) {
    it(`exposes ${name} on window`, () => {
      expect(typeof window[name]).toBe('function');
    });
  }
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
