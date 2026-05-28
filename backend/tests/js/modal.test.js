import { vi, describe, it, expect, beforeAll, beforeEach } from 'vitest';

vi.mock('@/zoom.js', () => ({
  visualToStored: vi.fn((x, y) => ({x, y})),
  resetZoom: vi.fn(),
}));

vi.mock('@/notes.js', () => ({
  noteCancel: vi.fn(),
  loadNotes: vi.fn(),
  initNotes: vi.fn(),
  renderPins: vi.fn(),
}));

vi.mock('@/api.js', () => ({
  updatePhoto: vi.fn().mockResolvedValue({
    id: 5, photo_type: 'overview', location_id: null, growing_units: [], original_filename: null, rotation: 0,
  }),
  createEvent: vi.fn().mockResolvedValue({id: 1}),
  getNotes: vi.fn().mockResolvedValue([]),
}));

let showModalPhoto, closeModal, toggleModalLogEvent, modalLogEvent, rotatePhoto, identityUpdate;
let state;

const PHOTO = {
  id: 5, url: '/photos/test.jpg', filename: 'test.jpg',
  captured_at: '2026-01-01T10:00:00Z', rotation: 90,
  source: 'pi', photo_type: 'overview', growing_units: [],
  original_filename: null, location_id: null,
};

beforeAll(async () => {
  document.body.innerHTML = `
    <div id="status"></div>
    <div id="modal" class="hidden">
      <div id="modal-img-wrap">
        <img id="modal-img" src="">
        <div id="note-pins"></div>
        <div id="rect-preview" style="display:none"></div>
      </div>
      <div id="modal-caption"></div>
      <div id="modal-log-event-panel" style="display:none"></div>
      <div id="modal-event-status"></div>
      <select id="modal-event-type">
        <option value="fed_liquid">Fed liquid</option>
        <option value="watered">Watered</option>
        <option value="potted_up">Potted up</option>
      </select>
      <input id="modal-event-note" value="">
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
    <div id="note-panel" class="hidden">
      <div id="note-panel-title"></div>
      <input id="note-text" value="">
      <button id="note-delete" style="display:none"></button>
    </div>
  `;

  ({showModalPhoto, closeModal, toggleModalLogEvent, modalLogEvent, rotatePhoto, identityUpdate} =
    await import('@/modal.js'));
  ({state} = await import('@/state.js'));
});

beforeEach(async () => {
  state.allPhotos = [PHOTO];
  state.currentIndex = 0;
  state.currentPhotoId = null;
  state.currentRotation = 0;
  vi.clearAllMocks();
  const api = await import('@/api.js');
  vi.mocked(api.updatePhoto).mockResolvedValue({
    id: 5, photo_type: 'overview', location_id: null, growing_units: [], original_filename: null, rotation: 0,
  });
  vi.mocked(api.createEvent).mockResolvedValue({id: 1});
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

  it('resets modal-event-type to first option (Bug B fix)', () => {
    document.getElementById('modal-event-type').selectedIndex = 2;
    showModalPhoto(0);
    expect(document.getElementById('modal-event-type').selectedIndex).toBe(0);
  });

  it('clears modal-event-note', () => {
    document.getElementById('modal-event-note').value = 'leftover';
    showModalPhoto(0);
    expect(document.getElementById('modal-event-note').value).toBe('');
  });

  it('sets modal-img src', () => {
    showModalPhoto(0);
    expect(document.getElementById('modal-img').src).toContain(PHOTO.url);
  });

  it('shows identity panel', () => {
    showModalPhoto(0);
    expect(document.getElementById('identity-panel').classList.contains('hidden')).toBe(false);
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

// ── toggleModalLogEvent ───────────────────────────────────

describe('toggleModalLogEvent', () => {
  it('shows the panel when it is hidden', () => {
    document.getElementById('modal-log-event-panel').style.display = 'none';
    toggleModalLogEvent();
    expect(document.getElementById('modal-log-event-panel').style.display).toBe('');
  });

  it('hides the panel when it is visible', () => {
    document.getElementById('modal-log-event-panel').style.display = '';
    toggleModalLogEvent();
    expect(document.getElementById('modal-log-event-panel').style.display).toBe('none');
  });

  it('clears the status text', () => {
    document.getElementById('modal-event-status').textContent = 'Logged.';
    toggleModalLogEvent();
    expect(document.getElementById('modal-event-status').textContent).toBe('');
  });
});

// ── modalLogEvent ─────────────────────────────────────────

describe('modalLogEvent', () => {
  it('does nothing when currentPhotoId is null', async () => {
    const {createEvent} = await import('@/api.js');
    state.currentPhotoId = null;
    await modalLogEvent();
    expect(createEvent).not.toHaveBeenCalled();
  });

  it('calls createEvent with event_type and photo_ids', async () => {
    const {createEvent} = await import('@/api.js');
    state.currentPhotoId = 5;
    document.getElementById('modal-event-type').value = 'watered';
    document.getElementById('modal-event-note').value = '';
    await modalLogEvent();
    expect(createEvent).toHaveBeenCalledWith({event_type: 'watered', photo_ids: [5]});
  });

  it('includes note_text when the note field is non-empty', async () => {
    const {createEvent} = await import('@/api.js');
    state.currentPhotoId = 5;
    document.getElementById('modal-event-type').value = 'watered';
    document.getElementById('modal-event-note').value = 'checked soil';
    await modalLogEvent();
    expect(createEvent).toHaveBeenCalledWith(
      expect.objectContaining({note_text: 'checked soil'})
    );
  });

  it('shows "Logged." on success', async () => {
    state.currentPhotoId = 5;
    document.getElementById('modal-event-note').value = '';
    await modalLogEvent();
    expect(document.getElementById('modal-event-status').textContent).toBe('Logged.');
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
