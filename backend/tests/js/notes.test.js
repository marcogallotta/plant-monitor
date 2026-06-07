import { vi, describe, it, expect, beforeAll, beforeEach } from 'vitest';

vi.mock('@/api.js', () => ({
  getNotes: vi.fn().mockResolvedValue([]),
  createNote: vi.fn().mockResolvedValue({id: 1}),
  updateNote: vi.fn().mockResolvedValue({}),
  deleteNote: vi.fn().mockResolvedValue(undefined),
}));

let renderPins, openCreateForm, noteSave, noteDelete, noteCancel, initNotes;
let state;

beforeAll(async () => {
  document.body.innerHTML = `
    <div id="status"></div>
    <div id="modal-img" style="position:absolute;left:0;top:0;width:100px;height:100px;"></div>
    <div id="note-pins"></div>
    <div id="note-panel" class="hidden">
      <div id="note-panel-title"></div>
      <input id="note-text" value="">
      <select id="note-unit"><option value="">— no unit —</option></select>
      <button id="note-delete" style="display:none"></button>
    </div>
    <div id="rect-preview" style="display:none"></div>
  `;

  ({renderPins, openCreateForm, noteSave, noteDelete, noteCancel, initNotes} =
    await import('@/notes.js'));
  ({state} = await import('@/state.js'));
  initNotes((x, y) => ({x, y}));
});

beforeEach(async () => {
  state.currentPhotoId = 42;
  state.currentNotes = [];
  state.pendingNote = null;
  state.wasDrag = false;
  vi.clearAllMocks();
  const api = await import('@/api.js');
  vi.mocked(api.createNote).mockResolvedValue({id: 1});
  vi.mocked(api.updateNote).mockResolvedValue({});
  vi.mocked(api.deleteNote).mockResolvedValue(undefined);
  vi.mocked(api.getNotes).mockResolvedValue([]);
  document.getElementById('note-text').value = '';
  document.getElementById('note-unit').innerHTML = '<option value="">— no unit —</option>';
  document.getElementById('note-panel').classList.add('hidden');
  document.getElementById('note-delete').style.display = 'none';
  state.allUnits = [];
});

// helper: add a growing-unit <option> so a value can be selected in jsdom
function addUnitOption(id, name) {
  state.allUnits.push({id, name});
  const opt = document.createElement('option');
  opt.value = String(id);
  opt.textContent = name;
  document.getElementById('note-unit').appendChild(opt);
}

// ── renderPins ────────────────────────────────────────────

describe('renderPins', () => {
  it('creates a note-pin element for a point note', () => {
    state.currentNotes = [{id: 1, note_text: 'pest', x: 0.3, y: 0.4, x2: null, y2: null}];
    renderPins();
    const pins = document.querySelectorAll('.note-pin');
    expect(pins).toHaveLength(1);
  });

  it('positions point note with left/top percentages', () => {
    state.currentNotes = [{id: 1, note_text: 'spot', x: 0.25, y: 0.75, x2: null, y2: null}];
    renderPins();
    const pin = document.querySelector('.note-pin');
    expect(pin.style.left).toBe('25%');
    expect(pin.style.top).toBe('75%');
  });

  it('creates a note-rect element for a region note', () => {
    state.currentNotes = [{id: 2, note_text: 'area', x: 0.1, y: 0.2, x2: 0.5, y2: 0.6}];
    renderPins();
    const rects = document.querySelectorAll('.note-rect');
    expect(rects).toHaveLength(1);
  });

  it('sizes the rect from min/max of the two corners', () => {
    state.currentNotes = [{id: 2, note_text: 'area', x: 0.5, y: 0.6, x2: 0.1, y2: 0.2}];
    renderPins();
    const rect = document.querySelector('.note-rect');
    expect(rect.style.left).toBe('10%');
    expect(rect.style.top).toBe('20%');
    expect(rect.style.width).toBe('40%');
    expect(rect.style.height).toBe('40%');
  });

  it('adds selected class to the point note matching pendingNote.noteId', () => {
    state.currentNotes = [
      {id: 1, note_text: 'a', x: 0.1, y: 0.1, x2: null, y2: null},
      {id: 2, note_text: 'b', x: 0.5, y: 0.5, x2: null, y2: null},
    ];
    state.pendingNote = {noteId: 2, x: 0.5, y: 0.5};
    renderPins();
    const pins = document.querySelectorAll('.note-pin');
    expect(pins[0].classList.contains('selected')).toBe(false);
    expect(pins[1].classList.contains('selected')).toBe(true);
  });

  it('clears previous pins before rendering', () => {
    state.currentNotes = [{id: 1, note_text: 'first', x: 0.1, y: 0.1, x2: null, y2: null}];
    renderPins();
    state.currentNotes = [];
    renderPins();
    expect(document.querySelectorAll('.note-pin')).toHaveLength(0);
  });

  it('labels a region note with its growing unit name', () => {
    state.allUnits = [{id: 5, name: 'Lemongrass'}];
    state.currentNotes = [{id: 2, note_text: null, growing_unit_id: 5, x: 0.1, y: 0.2, x2: 0.5, y2: 0.6}];
    renderPins();
    expect(document.querySelector('.note-rect-label').textContent).toBe('Lemongrass');
  });

  it('falls back to the index number when a region note has no unit', () => {
    state.currentNotes = [{id: 2, note_text: 'area', growing_unit_id: null, x: 0.1, y: 0.2, x2: 0.5, y2: 0.6}];
    renderPins();
    expect(document.querySelector('.note-rect-label').textContent).toBe('1');
  });
});

// ── openCreateForm ────────────────────────────────────────

describe('openCreateForm', () => {
  it('sets pendingNote with x and y', () => {
    openCreateForm(0.3, 0.7);
    expect(state.pendingNote).toMatchObject({x: 0.3, y: 0.7});
  });

  it('sets title to "New note" for a point', () => {
    openCreateForm(0.3, 0.7);
    expect(document.getElementById('note-panel-title').textContent).toBe('New note');
  });

  it('sets title to "New region note" when x2/y2 are provided', () => {
    openCreateForm(0.1, 0.2, 0.4, 0.6);
    expect(document.getElementById('note-panel-title').textContent).toBe('New region note');
  });

  it('stores null x2/y2 when not provided', () => {
    openCreateForm(0.5, 0.5);
    expect(state.pendingNote.x2).toBeNull();
    expect(state.pendingNote.y2).toBeNull();
  });

  it('clears the note text field', () => {
    document.getElementById('note-text').value = 'leftover';
    openCreateForm(0.5, 0.5);
    expect(document.getElementById('note-text').value).toBe('');
  });

  it('hides the delete button', () => {
    document.getElementById('note-delete').style.display = 'inline-block';
    openCreateForm(0.5, 0.5);
    expect(document.getElementById('note-delete').style.display).toBe('none');
  });

  it('shows the note panel', () => {
    document.getElementById('note-panel').classList.add('hidden');
    openCreateForm(0.5, 0.5);
    expect(document.getElementById('note-panel').classList.contains('hidden')).toBe(false);
  });
});

// ── noteSave ──────────────────────────────────────────────

describe('noteSave', () => {
  it('does nothing when pendingNote is null', async () => {
    const {createNote} = await import('@/api.js');
    state.pendingNote = null;
    await noteSave();
    expect(createNote).not.toHaveBeenCalled();
  });

  it('does nothing when both note text and unit are empty', async () => {
    const {createNote} = await import('@/api.js');
    state.pendingNote = {x: 0.5, y: 0.5, x2: null, y2: null};
    document.getElementById('note-text').value = '   ';
    await noteSave();
    expect(createNote).not.toHaveBeenCalled();
  });

  it('creates a unit-only note (no text) when a unit is selected', async () => {
    const {createNote} = await import('@/api.js');
    addUnitOption(5, 'Lemongrass');
    state.pendingNote = {x: 0.1, y: 0.2, x2: 0.5, y2: 0.6};
    document.getElementById('note-text').value = '';
    document.getElementById('note-unit').value = '5';
    await noteSave();
    const body = createNote.mock.calls[0][1];
    expect(body.growing_unit_id).toBe(5);
    expect(body).not.toHaveProperty('note_text');
  });

  it('sends growing_unit_id: null when no unit is selected', async () => {
    const {createNote} = await import('@/api.js');
    state.pendingNote = {x: 0.3, y: 0.4, x2: null, y2: null};
    document.getElementById('note-text').value = 'just text';
    await noteSave();
    expect(createNote.mock.calls[0][1].growing_unit_id).toBeNull();
  });

  it('calls createNote when there is no noteId', async () => {
    const {createNote} = await import('@/api.js');
    state.pendingNote = {x: 0.3, y: 0.4, x2: null, y2: null};
    document.getElementById('note-text').value = 'new note';
    await noteSave();
    expect(createNote).toHaveBeenCalledWith(42, expect.objectContaining({
      note_text: 'new note', x: 0.3, y: 0.4,
    }));
  });

  it('includes x2/y2 in createNote call when both are set', async () => {
    const {createNote} = await import('@/api.js');
    state.pendingNote = {x: 0.1, y: 0.2, x2: 0.5, y2: 0.6};
    document.getElementById('note-text').value = 'region note';
    await noteSave();
    expect(createNote).toHaveBeenCalledWith(42, expect.objectContaining({
      x2: 0.5, y2: 0.6,
    }));
  });

  it('omits x2/y2 from createNote call when they are null', async () => {
    const {createNote} = await import('@/api.js');
    state.pendingNote = {x: 0.3, y: 0.4, x2: null, y2: null};
    document.getElementById('note-text').value = 'point note';
    await noteSave();
    const body = createNote.mock.calls[0][1];
    expect(body).not.toHaveProperty('x2');
    expect(body).not.toHaveProperty('y2');
  });

  it('calls updateNote when noteId is present', async () => {
    const {updateNote} = await import('@/api.js');
    state.pendingNote = {noteId: 7, x: 0.3, y: 0.4, x2: null, y2: null};
    document.getElementById('note-text').value = 'edit';
    await noteSave();
    expect(updateNote).toHaveBeenCalledWith(7, expect.objectContaining({note_text: 'edit'}));
  });

  it('clears text on edit by sending note_text: null when a unit remains', async () => {
    const {updateNote} = await import('@/api.js');
    addUnitOption(5, 'Lemongrass');
    state.pendingNote = {noteId: 7, x: 0.3, y: 0.4, x2: null, y2: null};
    document.getElementById('note-text').value = '';
    document.getElementById('note-unit').value = '5';
    await noteSave();
    expect(updateNote.mock.calls[0][1].note_text).toBeNull();
  });
});

// ── noteDelete ────────────────────────────────────────────

describe('noteDelete', () => {
  it('does nothing when pendingNote has no noteId', async () => {
    const {deleteNote} = await import('@/api.js');
    state.pendingNote = {x: 0.5, y: 0.5, x2: null, y2: null};
    await noteDelete();
    expect(deleteNote).not.toHaveBeenCalled();
  });

  it('calls deleteNote with the noteId', async () => {
    const {deleteNote} = await import('@/api.js');
    state.pendingNote = {noteId: 3, x: 0.3, y: 0.4, x2: null, y2: null};
    await noteDelete();
    expect(deleteNote).toHaveBeenCalledWith(3);
  });
});

// ── noteCancel ────────────────────────────────────────────

describe('noteCancel', () => {
  it('clears pendingNote', () => {
    state.pendingNote = {x: 0.5, y: 0.5};
    noteCancel();
    expect(state.pendingNote).toBeNull();
  });

  it('hides the note panel', () => {
    document.getElementById('note-panel').classList.remove('hidden');
    noteCancel();
    expect(document.getElementById('note-panel').classList.contains('hidden')).toBe(true);
  });

  it('clears the note text', () => {
    document.getElementById('note-text').value = 'something';
    noteCancel();
    expect(document.getElementById('note-text').value).toBe('');
  });
});
