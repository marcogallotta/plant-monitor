import { vi, describe, it, expect, beforeAll, beforeEach } from 'vitest';

const mockLoadPhotos = vi.fn().mockResolvedValue(undefined);

vi.mock('@/api.js', () => ({
  uploadPhoto:         vi.fn().mockResolvedValue({}),
  scanCameraImport:    vi.fn().mockResolvedValue({ candidates: [], already_imported_count: 0, sources: [], warnings: [] }),
  importCameraPhotos:  vi.fn().mockResolvedValue({ created: [], skipped: [], failed: [] }),
  getThumbnailBatch:   vi.fn().mockResolvedValue({ thumbs: {} }),
}));

vi.mock('@/sdImportCore.js', () => ({
  isImportablePhoto: vi.fn(name => /\.(jpg|jpeg|arw|orf)$/i.test(name)),
  isRawPhoto:        vi.fn(name => /\.(arw|orf)$/i.test(name)),
  sortCameraFiles:   vi.fn(arr => [...arr].sort((a, b) => b.name.localeCompare(a.name))),
  detectSessionBoundary: vi.fn(() => -1),
  detectAllBoundaries:   vi.fn(() => []),
  scanForJpeg:       vi.fn(() => ({ jpeg: null, truncated: false })),
  deriveTimestamp:   vi.fn(() => ({ iso: '2026-05-28T10:00:00.000Z', badge: 'ok' })),
  buildUploadFormData: vi.fn(() => new FormData()),
}));

function makeFile(name, lastModified = 1748390400000) {
  return { name, lastModified, size: 1000, arrayBuffer: async () => new ArrayBuffer(0) };
}

function makeEvent(files) {
  return { target: { files } };
}

let toggleSdPanel, handleSdFolderInput, handleSdScan, sdLoadMore, sdSelectAllVisible, sdDeselectAll, sdUploadSelected, sdAddGroup, sdAddMore;
let core, api;

beforeAll(async () => {
  global.URL.createObjectURL = vi.fn(() => 'blob:mock');
  global.URL.revokeObjectURL = vi.fn();
  window.exifr = { parse: vi.fn().mockResolvedValue({}) };

  document.body.innerHTML = `
    <div id="sd-form">
      <label id="sd-toggle-label">▸ expand</label>
    </div>
    <button id="sd-scan-btn">Scan camera/card</button>
    <span id="sd-folder-status"></span>
    <div id="sd-grid-controls" style="display:none">
      <button id="sd-add-group-btn" style="display:none">Add group</button>
      <button id="sd-add-more-btn" style="display:none">Show older</button>
    </div>
    <div id="sd-load-more-row" style="display:none">
      <span id="sd-load-more-label"></span>
    </div>
    <div id="sd-grid"></div>
    <span id="sd-selected-count"></span>
    <div id="sd-upload-row" style="display:none">
      <button id="sd-upload-btn">Import</button>
    </div>
    <span id="sd-upload-status"></span>
    <select id="sd-photo-type"><option value="">—</option><option value="overview">overview</option></select>
  `;

  core = await import('@/sdImportCore.js');
  api  = await import('@/api.js');

  ({ toggleSdPanel, handleSdFolderInput, handleSdScan, sdLoadMore,
     sdSelectAllVisible, sdDeselectAll, sdUploadSelected,
     sdAddGroup, sdAddMore } = await import('@/sdImport.js'));

  const { initSdImport } = await import('@/sdImport.js');
  initSdImport(mockLoadPhotos);
});

beforeEach(() => {
  vi.clearAllMocks();
  mockLoadPhotos.mockResolvedValue(undefined);
  window.exifr.parse.mockResolvedValue({});
  vi.mocked(core.detectSessionBoundary).mockReturnValue(-1);
  vi.mocked(core.isImportablePhoto).mockImplementation(name => /\.(jpg|jpeg|arw|orf)$/i.test(name));
  vi.mocked(core.isRawPhoto).mockImplementation(name => /\.(arw|orf)$/i.test(name));
  vi.mocked(api.uploadPhoto).mockResolvedValue({});
  vi.mocked(api.scanCameraImport).mockResolvedValue({ candidates: [], already_imported_count: 0, sources: [], warnings: [] });
  vi.mocked(api.importCameraPhotos).mockResolvedValue({ created: [], skipped: [], failed: [] });
  vi.mocked(api.getThumbnailBatch).mockResolvedValue({ thumbs: {} });
  vi.mocked(core.detectAllBoundaries).mockReturnValue([]);
  document.getElementById('sd-folder-status').textContent = '';
  document.getElementById('sd-grid').innerHTML = '';
  document.getElementById('sd-grid-controls').style.display = 'none';
  document.getElementById('sd-load-more-row').style.display = 'none';
  document.getElementById('sd-upload-row').style.display = 'none';
  document.getElementById('sd-upload-status').textContent = '';
  document.getElementById('sd-upload-btn').disabled = false;
  document.getElementById('sd-photo-type').value = '';
  document.getElementById('sd-scan-btn').disabled = false;
});

// ── toggleSdPanel ─────────────────────────────────────────

describe('toggleSdPanel', () => {
  it('toggles open class on sd-form', () => {
    document.getElementById('sd-form').classList.remove('open');
    toggleSdPanel();
    expect(document.getElementById('sd-form').classList.contains('open')).toBe(true);
    toggleSdPanel();
    expect(document.getElementById('sd-form').classList.contains('open')).toBe(false);
  });

  it('updates label text when opening', () => {
    document.getElementById('sd-form').classList.remove('open');
    toggleSdPanel();
    expect(document.getElementById('sd-toggle-label').textContent).toBe('▾ collapse');
  });

  it('updates label text when closing', () => {
    document.getElementById('sd-form').classList.add('open');
    toggleSdPanel();
    expect(document.getElementById('sd-toggle-label').textContent).toBe('▸ expand');
  });
});

// ── handleSdFolderInput ───────────────────────────────────

describe('handleSdFolderInput', () => {
  it('calls _loadPhotos to refresh the uploaded set', async () => {
    await handleSdFolderInput(makeEvent([]));
    expect(mockLoadPhotos).toHaveBeenCalled();
  });

  it('shows "No photos found." when no importable files', async () => {
    vi.mocked(core.isImportablePhoto).mockReturnValue(false);
    await handleSdFolderInput(makeEvent([makeFile('document.pdf')]));
    expect(document.getElementById('sd-folder-status').textContent).toBe('No photos found.');
  });

  it('shows "All N already imported." when all photos already uploaded', async () => {
    const { state } = await import('@/state.js');
    state.allPhotos = [{ original_filename: 'DSC001.jpg' }];
    await handleSdFolderInput(makeEvent([makeFile('DSC001.jpg')]));
    expect(document.getElementById('sd-folder-status').textContent).toBe('All 1 already imported.');
    state.allPhotos = [];
  });

  it('shows photo count in status', async () => {
    await handleSdFolderInput(makeEvent([makeFile('DSC001.jpg'), makeFile('DSC002.jpg')]));
    expect(document.getElementById('sd-folder-status').textContent).toContain('2 photos');
  });

  it('uses singular "photo" for a single file', async () => {
    await handleSdFolderInput(makeEvent([makeFile('DSC001.jpg')]));
    const text = document.getElementById('sd-folder-status').textContent;
    expect(text).toContain('1 photo');
    expect(text).not.toContain('1 photos');
  });

  it('shows skip label when some files were already imported', async () => {
    const { state } = await import('@/state.js');
    state.allPhotos = [{ original_filename: 'DSC001.jpg' }];
    await handleSdFolderInput(makeEvent([makeFile('DSC001.jpg'), makeFile('DSC002.jpg')]));
    expect(document.getElementById('sd-folder-status').textContent).toContain('already imported');
    state.allPhotos = [];
  });

  it('shows grid controls when photos are found', async () => {
    await handleSdFolderInput(makeEvent([makeFile('DSC001.jpg')]));
    expect(document.getElementById('sd-grid-controls').style.display).not.toBe('none');
  });

  it('does not show grid controls when no photos found', async () => {
    vi.mocked(core.isImportablePhoto).mockReturnValue(false);
    await handleSdFolderInput(makeEvent([makeFile('document.pdf')]));
    expect(document.getElementById('sd-grid-controls').style.display).toBe('none');
  });

  it('adds thumb elements to the grid', async () => {
    await handleSdFolderInput(makeEvent([makeFile('DSC001.jpg'), makeFile('DSC002.jpg')]));
    expect(document.getElementById('sd-grid').querySelectorAll('.sd-thumb-wrap').length).toBe(2);
  });

  it('auto-selects the batch and shows batch label when session boundary detected', async () => {
    vi.mocked(core.detectAllBoundaries).mockReturnValue([1]);
    await handleSdFolderInput(makeEvent([
      makeFile('DSC001.jpg'), makeFile('DSC002.jpg'), makeFile('DSC003.jpg'),
    ]));
    expect(document.getElementById('sd-folder-status').textContent).toContain('in latest batch');
    const thumbs = document.getElementById('sd-grid').querySelectorAll('.sd-thumb-wrap');
    expect(thumbs[0].classList.contains('selected')).toBe(true);
    expect(thumbs[1].classList.contains('selected')).toBe(false);
  });
});

// ── sdSelectAllVisible / sdDeselectAll ────────────────────

describe('sdSelectAllVisible', () => {
  beforeEach(async () => {
    await handleSdFolderInput(makeEvent([makeFile('DSC001.jpg'), makeFile('DSC002.jpg')]));
  });

  it('marks all visible thumbs selected', () => {
    sdSelectAllVisible();
    document.getElementById('sd-grid').querySelectorAll('.sd-thumb-wrap').forEach(t => {
      expect(t.classList.contains('selected')).toBe(true);
    });
  });

  it('updates the selected count', () => {
    sdSelectAllVisible();
    expect(document.getElementById('sd-selected-count').textContent).toBe('2 selected');
  });

  it('shows the upload row', () => {
    sdSelectAllVisible();
    expect(document.getElementById('sd-upload-row').style.display).not.toBe('none');
  });
});

describe('sdDeselectAll', () => {
  beforeEach(async () => {
    await handleSdFolderInput(makeEvent([makeFile('DSC001.jpg'), makeFile('DSC002.jpg')]));
    sdSelectAllVisible();
  });

  it('removes selected class from all thumbs', () => {
    sdDeselectAll();
    document.getElementById('sd-grid').querySelectorAll('.sd-thumb-wrap').forEach(t => {
      expect(t.classList.contains('selected')).toBe(false);
    });
  });

  it('resets count to 0', () => {
    sdDeselectAll();
    expect(document.getElementById('sd-selected-count').textContent).toBe('0 selected');
  });

  it('hides the upload row', () => {
    sdDeselectAll();
    expect(document.getElementById('sd-upload-row').style.display).toBe('none');
  });
});

// ── sdLoadMore ────────────────────────────────────────────

describe('sdLoadMore', () => {
  it('appends more thumb elements beyond the initial page', async () => {
    const files = Array.from({ length: 25 }, (_, i) =>
      makeFile('DSC' + String(i).padStart(3, '0') + '.jpg'));
    await handleSdFolderInput(makeEvent(files));
    const before = document.getElementById('sd-grid').querySelectorAll('.sd-thumb-wrap').length;
    sdLoadMore();
    const after = document.getElementById('sd-grid').querySelectorAll('.sd-thumb-wrap').length;
    expect(after).toBeGreaterThan(before);
  });

  it('shows load-more row while remaining files exist', async () => {
    const files = Array.from({ length: 25 }, (_, i) =>
      makeFile('DSC' + String(i).padStart(3, '0') + '.jpg'));
    await handleSdFolderInput(makeEvent(files));
    expect(document.getElementById('sd-load-more-row').style.display).not.toBe('none');
  });

  it('hides load-more row after all files are shown', async () => {
    const files = Array.from({ length: 25 }, (_, i) =>
      makeFile('DSC' + String(i).padStart(3, '0') + '.jpg'));
    await handleSdFolderInput(makeEvent(files));
    sdLoadMore();
    expect(document.getElementById('sd-load-more-row').style.display).toBe('none');
  });

  it('does not cross into an unrevealed older session', async () => {
    // 3 batches: [0-24], [25-49], [50-54]. Only first two are revealed on init.
    vi.mocked(core.detectAllBoundaries).mockReturnValueOnce([25, 50]);
    const files = Array.from({ length: 55 }, (_, i) =>
      makeFile('DSC' + String(i).padStart(3, '0') + '.jpg'));
    await handleSdFolderInput(makeEvent(files));
    // After init: 25 (batch 0) + 20 (first page of batch 1) = 45 shown
    sdLoadMore(); // should show remaining 5 from batch 1, not 10 (5 + batch 2)
    const thumbs = document.getElementById('sd-grid').querySelectorAll('.sd-thumb-wrap');
    expect(thumbs.length).toBe(50);
  });

  it('hides load-more after exhausting the revealed session', async () => {
    vi.mocked(core.detectAllBoundaries).mockReturnValueOnce([25, 50]);
    const files = Array.from({ length: 55 }, (_, i) =>
      makeFile('DSC' + String(i).padStart(3, '0') + '.jpg'));
    await handleSdFolderInput(makeEvent(files));
    sdLoadMore();
    expect(document.getElementById('sd-load-more-row').style.display).toBe('none');
  });
});

// ── sdUploadSelected ──────────────────────────────────────

describe('sdUploadSelected', () => {
  beforeEach(async () => {
    await handleSdFolderInput(makeEvent([makeFile('DSC001.jpg'), makeFile('DSC002.jpg')]));
    mockLoadPhotos.mockClear();
  });

  it('does nothing when nothing is selected', async () => {
    sdDeselectAll();
    await sdUploadSelected();
    expect(api.uploadPhoto).not.toHaveBeenCalled();
  });

  it('calls uploadPhoto for each selected file', async () => {
    sdSelectAllVisible();
    await sdUploadSelected();
    expect(api.uploadPhoto).toHaveBeenCalledTimes(2);
  });

  it('passes photo type from sd-photo-type select to buildUploadFormData', async () => {
    document.getElementById('sd-photo-type').value = 'overview';
    sdSelectAllVisible();
    await sdUploadSelected();
    expect(core.buildUploadFormData).toHaveBeenCalledWith(
      expect.anything(), expect.any(String), expect.any(String), 'overview', expect.any(Number), expect.any(Number),
    );
  });

  it('calls _loadPhotos after at least one successful upload', async () => {
    sdSelectAllVisible();
    await sdUploadSelected();
    expect(mockLoadPhotos).toHaveBeenCalled();
  });

  it('does not call _loadPhotos when all uploads fail', async () => {
    vi.mocked(api.uploadPhoto).mockRejectedValue(new Error('network error'));
    sdSelectAllVisible();
    await sdUploadSelected();
    expect(mockLoadPhotos).not.toHaveBeenCalled();
  });

  it('shows uploaded count in final status', async () => {
    sdSelectAllVisible();
    await sdUploadSelected();
    expect(document.getElementById('sd-upload-status').textContent).toContain('uploaded');
  });

  it('includes failure count in status when some uploads fail', async () => {
    vi.mocked(api.uploadPhoto).mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('fail'));
    sdSelectAllVisible();
    await sdUploadSelected();
    expect(document.getElementById('sd-upload-status').textContent).toContain('failed');
  });

  it('re-enables the upload button after completion', async () => {
    sdSelectAllVisible();
    await sdUploadSelected();
    expect(document.getElementById('sd-upload-btn').disabled).toBe(false);
  });
});

// ── handleSdScan (backend mode) ───────────────────────────

function makeCandidate(filename, overrides = {}) {
  return {
    id: 'fileid_' + filename,
    filename,
    is_raw: /\.(arw|orf)$/i.test(filename),
    thumbnail_url: '/camera-import/thumbs/fileid_' + filename,
    captured_at: '2026-05-28T10:00:00Z',
    mtime_ms: 1748390400000,
    already_imported: false,
    ...overrides,
  };
}

describe('handleSdScan', () => {
  it('calls scanCameraImport API', async () => {
    await handleSdScan();
    expect(api.scanCameraImport).toHaveBeenCalled();
  });

  it('shows "No camera/card photos found." when no candidates', async () => {
    await handleSdScan();
    expect(document.getElementById('sd-folder-status').textContent).toContain('No camera/card photos found.');
  });

  it('shows all-imported message when no candidates but imported count > 0', async () => {
    vi.mocked(api.scanCameraImport).mockResolvedValue({
      candidates: [], already_imported_count: 5, sources: [], warnings: [],
    });
    await handleSdScan();
    expect(document.getElementById('sd-folder-status').textContent).toContain('All 5 already imported.');
  });

  it('renders thumbnail cards for candidates', async () => {
    vi.mocked(api.scanCameraImport).mockResolvedValue({
      candidates: [makeCandidate('DSC001.JPG'), makeCandidate('DSC002.JPG')],
      already_imported_count: 0, sources: [{label: 'TESTCARD'}], warnings: [],
    });
    await handleSdScan();
    expect(document.getElementById('sd-grid').querySelectorAll('.sd-thumb-wrap').length).toBe(2);
  });

  it('shows grid controls when candidates found', async () => {
    vi.mocked(api.scanCameraImport).mockResolvedValue({
      candidates: [makeCandidate('DSC001.JPG')],
      already_imported_count: 0, sources: [{label: 'CARD'}], warnings: [],
    });
    await handleSdScan();
    expect(document.getElementById('sd-grid-controls').style.display).not.toBe('none');
  });

  it('auto-selects latest batch using mtime_ms', async () => {
    vi.mocked(core.detectAllBoundaries).mockReturnValue([1]);
    vi.mocked(api.scanCameraImport).mockResolvedValue({
      candidates: [makeCandidate('DSC001.JPG'), makeCandidate('DSC002.JPG'), makeCandidate('DSC003.JPG')],
      already_imported_count: 0, sources: [{label: 'CARD'}], warnings: [],
    });
    await handleSdScan();
    const thumbs = document.getElementById('sd-grid').querySelectorAll('.sd-thumb-wrap');
    expect(thumbs[0].classList.contains('selected')).toBe(true);
    expect(thumbs[1].classList.contains('selected')).toBe(false);
  });

  it('shows error status when scan API fails', async () => {
    vi.mocked(api.scanCameraImport).mockRejectedValue(new Error('network error'));
    await handleSdScan();
    expect(document.getElementById('sd-folder-status').textContent).toContain('Scan failed');
  });

  it('re-enables scan button after failure', async () => {
    vi.mocked(api.scanCameraImport).mockRejectedValue(new Error('fail'));
    await handleSdScan();
    expect(document.getElementById('sd-scan-btn').disabled).toBe(false);
  });
});

// ── sdUploadSelected in backend mode ─────────────────────

async function setupBackendMode(candidates) {
  vi.mocked(api.scanCameraImport).mockResolvedValue({
    candidates, already_imported_count: 0, sources: [{label: 'CARD'}], warnings: [],
  });
  await handleSdScan();
  sdSelectAllVisible();
}

describe('sdUploadSelected (backend mode)', () => {
  it('calls importCameraPhotos with selected file IDs', async () => {
    await setupBackendMode([makeCandidate('DSC001.JPG'), makeCandidate('DSC002.JPG')]);
    await sdUploadSelected();
    expect(api.importCameraPhotos).toHaveBeenCalledWith(
      expect.objectContaining({ file_ids: expect.arrayContaining(['fileid_DSC001.JPG', 'fileid_DSC002.JPG']) })
    );
  });

  it('does not call uploadPhoto in backend mode', async () => {
    await setupBackendMode([makeCandidate('DSC001.JPG')]);
    await sdUploadSelected();
    expect(api.uploadPhoto).not.toHaveBeenCalled();
  });

  it('shows imported count in status', async () => {
    await setupBackendMode([makeCandidate('DSC001.JPG')]);
    vi.mocked(api.importCameraPhotos).mockResolvedValue({
      created: [{ file_id: 'fileid_DSC001.JPG' }], skipped: [], failed: [],
    });
    await sdUploadSelected();
    expect(document.getElementById('sd-upload-status').textContent).toContain('1 imported');
  });

  it('shows skipped count when files already imported', async () => {
    await setupBackendMode([makeCandidate('DSC001.JPG')]);
    vi.mocked(api.importCameraPhotos).mockResolvedValue({
      created: [], skipped: [{ file_id: 'fileid_DSC001.JPG', reason: 'already_imported' }], failed: [],
    });
    await sdUploadSelected();
    expect(document.getElementById('sd-upload-status').textContent).toContain('skipped');
  });

  it('shows failed count on error', async () => {
    await setupBackendMode([makeCandidate('DSC001.JPG')]);
    vi.mocked(api.importCameraPhotos).mockResolvedValue({
      created: [], skipped: [], failed: [{ file_id: 'fileid_DSC001.JPG', reason: 'raw_preview_not_found' }],
    });
    await sdUploadSelected();
    expect(document.getElementById('sd-upload-status').textContent).toContain('failed');
  });

  it('calls _loadPhotos after successful import', async () => {
    await setupBackendMode([makeCandidate('DSC001.JPG')]);
    vi.mocked(api.importCameraPhotos).mockResolvedValue({
      created: [{ file_id: 'fileid_DSC001.JPG' }], skipped: [], failed: [],
    });
    await sdUploadSelected();
    expect(mockLoadPhotos).toHaveBeenCalled();
  });

  it('does not call _loadPhotos when nothing was created', async () => {
    await setupBackendMode([makeCandidate('DSC001.JPG')]);
    vi.mocked(api.importCameraPhotos).mockResolvedValue({
      created: [], skipped: [], failed: [{ file_id: 'fileid_DSC001.JPG', reason: 'error' }],
    });
    mockLoadPhotos.mockClear();
    await sdUploadSelected();
    expect(mockLoadPhotos).not.toHaveBeenCalled();
  });

  it('re-enables upload button after completion', async () => {
    await setupBackendMode([makeCandidate('DSC001.JPG')]);
    await sdUploadSelected();
    expect(document.getElementById('sd-upload-btn').disabled).toBe(false);
  });
});
