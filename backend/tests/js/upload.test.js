import { vi, describe, it, expect, beforeAll, beforeEach, afterEach } from 'vitest';
import { makeFetchMock } from './fetchHelper.js';

let toggleUploadPanel, submitManualUpload, initUpload;
let fetchMock;

beforeAll(async () => {
  document.body.innerHTML = `
    <div id="upload-form">
      <label id="upload-toggle-label">▸ expand</label>
      <input id="upload-image" type="file">
      <input id="upload-captured-at" value="">
      <select id="upload-photo-type"><option value="">—</option><option value="overview">Overview</option></select>
      <select id="upload-location"><option value="">—</option></select>
      <select id="upload-units" multiple></select>
      <input id="upload-note" value="">
      <span id="upload-status"></span>
    </div>
  `;

  ({toggleUploadPanel, submitManualUpload, initUpload} = await import('@/upload.js'));
});

beforeEach(() => {
  fetchMock = makeFetchMock([
    {method: 'POST', url: '/manual-photos', body: {id: 1}},
  ]);
  vi.stubGlobal('fetch', fetchMock);
  initUpload(vi.fn());
  document.getElementById('upload-status').textContent = '';
  document.getElementById('upload-captured-at').value = '';
  document.getElementById('upload-photo-type').value = '';
  document.getElementById('upload-location').value = '';
  document.getElementById('upload-note').value = '';
  Array.from(document.getElementById('upload-units').options).forEach(o => { o.selected = false; });
});

afterEach(() => vi.unstubAllGlobals());

// ── toggleUploadPanel ─────────────────────────────────────

describe('toggleUploadPanel', () => {
  it('toggles the open class on the form', () => {
    document.getElementById('upload-form').classList.remove('open');
    toggleUploadPanel();
    expect(document.getElementById('upload-form').classList.contains('open')).toBe(true);
    toggleUploadPanel();
    expect(document.getElementById('upload-form').classList.contains('open')).toBe(false);
  });

  it('sets label to "▾ collapse" when opening', () => {
    document.getElementById('upload-form').classList.remove('open');
    toggleUploadPanel();
    expect(document.getElementById('upload-toggle-label').textContent).toBe('▾ collapse');
  });

  it('sets label to "▸ expand" when closing', () => {
    document.getElementById('upload-form').classList.add('open');
    toggleUploadPanel();
    expect(document.getElementById('upload-toggle-label').textContent).toBe('▸ expand');
  });
});

// ── submitManualUpload — no file selected ─────────────────

describe('submitManualUpload — no file selected', () => {
  it('shows "Choose an image first." when no file is selected', async () => {
    await submitManualUpload();
    expect(document.getElementById('upload-status').textContent).toBe('Choose an image first.');
  });

  it('does not call POST /manual-photos when no file is selected', async () => {
    await submitManualUpload();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('submitManualUpload — with file', () => {
  let fileInput;

  beforeEach(() => {
    fileInput = document.getElementById('upload-image');
    const mockFile = new File(['bytes'], 'plant.jpg', {type: 'image/jpeg'});
    Object.defineProperty(fileInput, 'files', {value: [mockFile], configurable: true});
  });

  it('POSTs to /manual-photos', async () => {
    await submitManualUpload();
    expect(fetchMock).toHaveBeenCalledWith('/manual-photos', expect.objectContaining({method: 'POST'}));
  });

  it('sends the image in the FormData', async () => {
    await submitManualUpload();
    const call = fetchMock.mock.calls.find(([u]) => u === '/manual-photos');
    expect(call[1].body.get('image')).not.toBeNull();
  });

  it('includes captured_at as ISO string when provided', async () => {
    document.getElementById('upload-captured-at').value = '2026-05-28T10:00';
    await submitManualUpload();
    const call = fetchMock.mock.calls.find(([u]) => u === '/manual-photos');
    expect(call[1].body.get('captured_at')).toMatch(/^2026-05-28T/);
  });

  it('omits captured_at when field is empty', async () => {
    document.getElementById('upload-captured-at').value = '';
    await submitManualUpload();
    const call = fetchMock.mock.calls.find(([u]) => u === '/manual-photos');
    expect(call[1].body.get('captured_at')).toBeNull();
  });

  it('includes photo_type when selected', async () => {
    document.getElementById('upload-photo-type').value = 'overview';
    await submitManualUpload();
    const call = fetchMock.mock.calls.find(([u]) => u === '/manual-photos');
    expect(call[1].body.get('photo_type')).toBe('overview');
  });

  it('includes note_text when filled in', async () => {
    document.getElementById('upload-note').value = 'new sprout';
    await submitManualUpload();
    const call = fetchMock.mock.calls.find(([u]) => u === '/manual-photos');
    expect(call[1].body.get('note_text')).toBe('new sprout');
  });

  it('shows "Uploaded." and clears fields on success', async () => {
    document.getElementById('upload-note').value = 'something';
    await submitManualUpload();
    expect(document.getElementById('upload-status').textContent).toBe('Uploaded.');
    expect(document.getElementById('upload-note').value).toBe('');
  });

  it('shows error message when POST /manual-photos fails', async () => {
    fetchMock.mockResolvedValueOnce({ok: false, status: 500, json: () => Promise.resolve({detail: 'network error'})});
    await submitManualUpload();
    expect(document.getElementById('upload-status').textContent).toContain('network error');
  });
});
