import { vi, describe, it, expect, beforeAll, beforeEach } from 'vitest';

vi.mock('@/api.js', () => ({
  uploadPhoto: vi.fn().mockResolvedValue({id: 1}),
}));

let toggleUploadPanel, submitManualUpload, initUpload;

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

beforeEach(async () => {
  const mockLoadPhotos = vi.fn();
  initUpload(mockLoadPhotos);
  vi.clearAllMocks();
  const api = await import('@/api.js');
  vi.mocked(api.uploadPhoto).mockResolvedValue({id: 1});
  document.getElementById('upload-status').textContent = '';
  document.getElementById('upload-captured-at').value = '';
  document.getElementById('upload-photo-type').value = '';
  document.getElementById('upload-location').value = '';
  document.getElementById('upload-note').value = '';
  Array.from(document.getElementById('upload-units').options).forEach(o => { o.selected = false; });
});

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

// ── submitManualUpload ────────────────────────────────────

describe('submitManualUpload — no file selected', () => {
  it('shows "Choose an image first." when no file is selected', async () => {
    await submitManualUpload();
    expect(document.getElementById('upload-status').textContent).toBe('Choose an image first.');
  });

  it('does not call uploadPhoto when no file is selected', async () => {
    const {uploadPhoto} = await import('@/api.js');
    await submitManualUpload();
    expect(uploadPhoto).not.toHaveBeenCalled();
  });
});

describe('submitManualUpload — with file', () => {
  let fileInput;

  beforeEach(() => {
    fileInput = document.getElementById('upload-image');
    const mockFile = new File(['bytes'], 'plant.jpg', {type: 'image/jpeg'});
    Object.defineProperty(fileInput, 'files', {value: [mockFile], configurable: true});
  });

  it('calls uploadPhoto with a FormData containing the image', async () => {
    const {uploadPhoto} = await import('@/api.js');
    await submitManualUpload();
    expect(uploadPhoto).toHaveBeenCalledOnce();
    const fd = uploadPhoto.mock.calls[0][0];
    expect(fd.get('image')).not.toBeNull();
  });

  it('includes captured_at as ISO string when provided', async () => {
    const {uploadPhoto} = await import('@/api.js');
    document.getElementById('upload-captured-at').value = '2026-05-28T10:00';
    await submitManualUpload();
    const fd = uploadPhoto.mock.calls[0][0];
    expect(fd.get('captured_at')).toMatch(/^2026-05-28T/);
  });

  it('omits captured_at when field is empty', async () => {
    const {uploadPhoto} = await import('@/api.js');
    document.getElementById('upload-captured-at').value = '';
    await submitManualUpload();
    const fd = uploadPhoto.mock.calls[0][0];
    expect(fd.get('captured_at')).toBeNull();
  });

  it('includes photo_type when selected', async () => {
    const {uploadPhoto} = await import('@/api.js');
    document.getElementById('upload-photo-type').value = 'overview';
    await submitManualUpload();
    const fd = uploadPhoto.mock.calls[0][0];
    expect(fd.get('photo_type')).toBe('overview');
  });

  it('includes note_text when filled in', async () => {
    const {uploadPhoto} = await import('@/api.js');
    document.getElementById('upload-note').value = 'new sprout';
    await submitManualUpload();
    const fd = uploadPhoto.mock.calls[0][0];
    expect(fd.get('note_text')).toBe('new sprout');
  });

  it('shows "Uploaded." and clears fields on success', async () => {
    document.getElementById('upload-note').value = 'something';
    await submitManualUpload();
    expect(document.getElementById('upload-status').textContent).toBe('Uploaded.');
    expect(document.getElementById('upload-note').value).toBe('');
  });

  it('shows error message when uploadPhoto rejects', async () => {
    const {uploadPhoto} = await import('@/api.js');
    uploadPhoto.mockRejectedValueOnce(new Error('network error'));
    await submitManualUpload();
    expect(document.getElementById('upload-status').textContent).toContain('network error');
  });
});
