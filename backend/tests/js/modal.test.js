import { vi, describe, it, expect, beforeAll, beforeEach } from 'vitest';

vi.mock('@/zoom.js', () => ({
  visualToStored: vi.fn((x, y) => ({x, y})),
  resetZoom: vi.fn(),
}));

vi.mock('@/labels.js', () => ({
  renderLabelSection: vi.fn(),
}));

vi.mock('@/notes.js', () => ({
  noteCancel: vi.fn(),
  loadNotes: vi.fn(),
  initNotes: vi.fn(),
  renderPins: vi.fn(),
}));

vi.mock('@/api.js', () => ({
  updatePhoto: vi.fn().mockResolvedValue({
    id: 5, photo_type: 'overview', location_id: null, growing_units: [], labels: [], original_filename: null, rotation: 0,
  }),
  getNotes: vi.fn().mockResolvedValue([]),
  createEvent: vi.fn().mockResolvedValue({id: 1}),
}));

let showModalPhoto, closeModal, rotatePhoto, identityUpdate, toggleModalLogEvent, logModalEvent;
let state;

const PHOTO = {
  id: 5, url: '/photos/test.jpg', filename: 'test.jpg',
  captured_at: '2026-01-01T10:00:00Z', rotation: 90,
  source: 'pi', photo_type: 'overview', growing_units: [],
  labels: [], original_filename: null, location_id: null,
};

beforeAll(async () => {
  document.body.innerHTML = `
    <div id="status"></div>
    <div id="modal" class="hidden">
      <button id="modal-prev" disabled></button>
      <button id="modal-next" disabled></button>
      <div id="modal-img-wrap">
        <img id="modal-img" src="">
        <div id="note-pins"></div>
        <div id="rect-preview" style="display:none"></div>
      </div>
      <div id="modal-caption"></div>
      <div id="identity-panel" class="hidden">
        <span id="id-source"></span>
        <select id="id-type-select">
          <option value="">—</option>
          <option value="overview">Overview</option>
        </select>
        <select id="id-location-select">
          <option value="">—</option>
        </select>
        <select id="id-units-select" multiple></select>
        <div id="id-original-row" style="display:none">
          <span id="id-original"></span>
        </div>
      </div>
    </div>
      <div id="modal-event-panel" class="hidden">
        <select id="modal-event-type">
          <option value="">— select type —</option>
          <option value="watered">Watered</option>
          <option value="fed_liquid">Fed liquid</option>
        </select>
        <textarea id="modal-event-note"></textarea>
      </div>
      <span id="modal-event-status"></span>
    <div id="note-panel" class="hidden">
      <div id="note-panel-title"></div>
      <input id="note-text" value="">
      <button id="note-delete" style="display:none"></button>
    </div>
  `;

  ({showModalPhoto, closeModal, rotatePhoto, identityUpdate, toggleModalLogEvent, logModalEvent} =
    await import('@/modal.js'));
  ({state} = await import('@/state.js'));
});

beforeEach(async () => {
  state.allPhotos = [PHOTO];
  state.allLabels = [{id: 1, name: 'aphids'}, {id: 2, name: 'yellowing'}];
  state.currentIndex = 0;
  state.currentPhotoId = null;
  state.currentRotation = 0;
  vi.clearAllMocks();
  const api = await import('@/api.js');
  vi.mocked(api.updatePhoto).mockResolvedValue({
    id: 5, photo_type: 'overview', location_id: null, growing_units: [], labels: [], original_filename: null, rotation: 0,
  });
});

// ── rotatePhoto ───────────────────────────────────────────

describe('rotatePhoto', () => {
  it('increments currentRotation by delta', async () => {
    state.currentPhotoId = 5;
    state.currentIndex = 0;
    state.currentRotation = 0;
    await rotatePhoto(90);
    expect(state.currentRotation).toBe(90);
  });

  it('wraps 360 → 0', async () => {
    state.currentPhotoId = 5;
    state.currentRotation = 270;
    await rotatePhoto(90);
    expect(state.currentRotation).toBe(0);
  });

  it('wraps negative delta correctly', async () => {
    state.currentPhotoId = 5;
    state.currentRotation = 0;
    await rotatePhoto(-90);
    expect(state.currentRotation).toBe(270);
  });

  it('calls updatePhoto with the new rotation', async () => {
    const {updatePhoto} = await import('@/api.js');
    state.currentPhotoId = 5;
    state.currentRotation = 0;
    await rotatePhoto(90);
    expect(updatePhoto).toHaveBeenCalledWith(5, {rotation: 90});
  });
});

// ── showModalPhoto ────────────────────────────────────────

describe('showModalPhoto', () => {
  it('sets state.currentPhotoId from the photo', () => {
    showModalPhoto(0);
    expect(state.currentPhotoId).toBe(PHOTO.id);
  });

  it('sets state.currentRotation from the photo', () => {
    showModalPhoto(0);
    expect(state.currentRotation).toBe(PHOTO.rotation);
  });

  it('sets modal-img src', () => {
    showModalPhoto(0);
    expect(document.getElementById('modal-img').src).toContain(PHOTO.url);
  });

  it('shows identity panel', () => {
    showModalPhoto(0);
    expect(document.getElementById('identity-panel').classList.contains('hidden')).toBe(false);
  });

  it('calls renderLabelSection with the photo', async () => {
    const {renderLabelSection} = await import('@/labels.js');
    showModalPhoto(0);
    expect(renderLabelSection).toHaveBeenCalledWith(PHOTO);
  });

  it('hides modal-event-panel', () => {
    document.getElementById('modal-event-panel').classList.remove('hidden');
    showModalPhoto(0);
    expect(document.getElementById('modal-event-panel').classList.contains('hidden')).toBe(true);
  });

  it('clears modal-event-status', () => {
    document.getElementById('modal-event-status').textContent = 'Logged.';
    showModalPhoto(0);
    expect(document.getElementById('modal-event-status').textContent).toBe('');
  });

  it('disables modal-prev when at first photo', () => {
    state.allPhotos = [PHOTO, PHOTO];
    showModalPhoto(0);
    expect(document.getElementById('modal-prev').disabled).toBe(true);
    expect(document.getElementById('modal-next').disabled).toBe(false);
  });

  it('disables modal-next when at last photo', () => {
    state.allPhotos = [PHOTO, PHOTO];
    showModalPhoto(1);
    expect(document.getElementById('modal-prev').disabled).toBe(false);
    expect(document.getElementById('modal-next').disabled).toBe(true);
  });

  it('enables both buttons when in the middle', () => {
    state.allPhotos = [PHOTO, PHOTO, PHOTO];
    showModalPhoto(1);
    expect(document.getElementById('modal-prev').disabled).toBe(false);
    expect(document.getElementById('modal-next').disabled).toBe(false);
  });
});

// ── closeModal ────────────────────────────────────────────

describe('closeModal', () => {
  it('sets currentPhotoId to null', () => {
    state.currentPhotoId = 5;
    closeModal();
    expect(state.currentPhotoId).toBeNull();
  });

  it('clears currentNotes', () => {
    state.currentNotes = [{id: 1}];
    closeModal();
    expect(state.currentNotes).toEqual([]);
  });

  it('adds hidden class to modal', () => {
    document.getElementById('modal').classList.remove('hidden');
    closeModal();
    expect(document.getElementById('modal').classList.contains('hidden')).toBe(true);
  });

  it('hides identity panel', () => {
    document.getElementById('identity-panel').classList.remove('hidden');
    closeModal();
    expect(document.getElementById('identity-panel').classList.contains('hidden')).toBe(true);
  });
});


// ── identityUpdate ────────────────────────────────────────

describe('identityUpdate', () => {
  it('does nothing when currentPhotoId is null', async () => {
    const {updatePhoto} = await import('@/api.js');
    state.currentPhotoId = null;
    await identityUpdate();
    expect(updatePhoto).not.toHaveBeenCalled();
  });

  it('calls updatePhoto with photo_type from select', async () => {
    const {updatePhoto} = await import('@/api.js');
    state.currentPhotoId = 5;
    state.allPhotos = [PHOTO];
    document.getElementById('id-type-select').value = 'overview';
    document.getElementById('id-location-select').value = '';
    await identityUpdate();
    expect(updatePhoto).toHaveBeenCalledWith(
      5,
      expect.objectContaining({photo_type: 'overview'})
    );
  });

  it('sends null for empty location_id', async () => {
    const {updatePhoto} = await import('@/api.js');
    state.currentPhotoId = 5;
    state.allPhotos = [PHOTO];
    document.getElementById('id-location-select').value = '';
    await identityUpdate();
    expect(updatePhoto).toHaveBeenCalledWith(
      5,
      expect.objectContaining({location_id: null})
    );
  });
});

// ── toggleModalLogEvent ───────────────────────────────────

describe('toggleModalLogEvent', () => {
  it('shows the panel when it is hidden', () => {
    document.getElementById('modal-event-panel').classList.add('hidden');
    toggleModalLogEvent();
    expect(document.getElementById('modal-event-panel').classList.contains('hidden')).toBe(false);
  });

  it('hides the panel when it is visible', () => {
    document.getElementById('modal-event-panel').classList.remove('hidden');
    toggleModalLogEvent();
    expect(document.getElementById('modal-event-panel').classList.contains('hidden')).toBe(true);
  });

  it('clears status when opening', () => {
    document.getElementById('modal-event-panel').classList.add('hidden');
    document.getElementById('modal-event-status').textContent = 'Logged.';
    toggleModalLogEvent();
    expect(document.getElementById('modal-event-status').textContent).toBe('');
  });
});

// ── logModalEvent ─────────────────────────────────────────

describe('logModalEvent', () => {
  beforeEach(async () => {
    state.currentPhotoId = 5;
    document.getElementById('modal-event-type').value = 'watered';
    document.getElementById('modal-event-note').value = '';
    document.getElementById('modal-event-status').textContent = '';
    document.getElementById('modal-event-panel').classList.remove('hidden');
    const api = await import('@/api.js');
    vi.mocked(api.createEvent).mockResolvedValue({id: 1});
  });

  it('shows error and does not call createEvent when no type selected', async () => {
    const {createEvent} = await import('@/api.js');
    document.getElementById('modal-event-type').value = '';
    await logModalEvent();
    expect(document.getElementById('modal-event-status').textContent).toBeTruthy();
    expect(createEvent).not.toHaveBeenCalled();
  });

  it('calls createEvent with event_type and photo_ids', async () => {
    const {createEvent} = await import('@/api.js');
    await logModalEvent();
    expect(createEvent).toHaveBeenCalledWith(expect.objectContaining({
      event_type: 'watered',
      photo_ids: [5],
    }));
  });

  it('includes note_text when note is provided', async () => {
    const {createEvent} = await import('@/api.js');
    document.getElementById('modal-event-note').value = 'big drink';
    await logModalEvent();
    expect(createEvent).toHaveBeenCalledWith(expect.objectContaining({note_text: 'big drink'}));
  });

  it('hides the panel after success', async () => {
    await logModalEvent();
    expect(document.getElementById('modal-event-panel').classList.contains('hidden')).toBe(true);
  });

  it('shows "Logged." after success', async () => {
    await logModalEvent();
    expect(document.getElementById('modal-event-status').textContent).toBe('Logged.');
  });

  it('shows error message on api failure', async () => {
    const {createEvent} = await import('@/api.js');
    createEvent.mockRejectedValueOnce(new Error('server error'));
    await logModalEvent();
    expect(document.getElementById('modal-event-status').textContent).toContain('server error');
  });
});
