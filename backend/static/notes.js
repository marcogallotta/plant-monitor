import { state } from './state.js';
import { getNotes, createNote, updateNote, deleteNote } from './api.js';
import { setStatus } from './utils.js';

let _visualToStored;

export function initNotes(visualToStored) {
  _visualToStored = visualToStored;
}

export async function loadNotes() {
  if (!state.currentPhotoId) return;
  try {
    state.currentNotes = await getNotes(state.currentPhotoId);
    renderPins();
  } catch (e) { setStatus('Failed to load notes: ' + e.message); }
}

export function renderPins() {
  const container = document.getElementById('note-pins');
  container.innerHTML = '';
  const isSelected = function(note) { return state.pendingNote && state.pendingNote.noteId === note.id; };
  state.currentNotes.forEach(function(note, i) {
    const el = document.createElement('div');
    if (note.x2 != null && note.y2 != null) {
      const x1 = Math.min(note.x, note.x2), y1 = Math.min(note.y, note.y2);
      const x2 = Math.max(note.x, note.x2), y2 = Math.max(note.y, note.y2);
      el.className = 'note-rect';
      el.style.left   = (x1 * 100) + '%';
      el.style.top    = (y1 * 100) + '%';
      el.style.width  = ((x2 - x1) * 100) + '%';
      el.style.height = ((y2 - y1) * 100) + '%';
      if (isSelected(note)) {
        el.style.border = '3px dashed #ff0';
        el.style.background = 'rgba(255,255,0,0.25)';
        el.style.zIndex = '10';
      }
      const label = document.createElement('span');
      label.className = 'note-rect-label';
      label.textContent = i + 1;
      el.appendChild(label);
    } else {
      el.className = 'note-pin' + (isSelected(note) ? ' selected' : '');
      el.style.left = (note.x * 100) + '%';
      el.style.top  = (note.y * 100) + '%';
      el.textContent = i + 1;
    }
    el.title = note.note_text;
    el.addEventListener('click', function(e) { e.stopPropagation(); openEditForm(note); });
    container.appendChild(el);
  });
}

export function modalImgClick(e) {
  if (state.wasDrag) { state.wasDrag = false; return; }
  if (!state.currentPhotoId) return;
  const img = document.getElementById('modal-img');
  const r = img.getBoundingClientRect();
  if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) return;
  const raw = _visualToStored(
    (e.clientX - r.left) / r.width,
    (e.clientY - r.top)  / r.height
  );
  openCreateForm(raw.x, raw.y);
}

export function openCreateForm(x, y, x2, y2) {
  state.pendingNote = {x: x, y: y, x2: x2 != null ? x2 : null, y2: y2 != null ? y2 : null};
  var isRect = x2 != null && y2 != null;
  document.getElementById('note-panel-title').textContent = isRect ? 'New region note' : 'New note';
  document.getElementById('note-text').value = '';
  document.getElementById('note-delete').style.display = 'none';
  document.getElementById('note-panel').classList.remove('hidden');
  document.getElementById('note-text').focus();
  renderPins();
}

function openEditForm(note) {
  state.pendingNote = {noteId: note.id, x: note.x, y: note.y, x2: note.x2, y2: note.y2};
  document.getElementById('note-panel-title').textContent = 'Edit note';
  document.getElementById('note-text').value = note.note_text;
  document.getElementById('note-delete').style.display = 'inline-block';
  document.getElementById('note-panel').classList.remove('hidden');
  document.getElementById('note-text').focus();
  renderPins();
}

export async function noteSave() {
  if (!state.pendingNote || !state.currentPhotoId) return;
  const text = document.getElementById('note-text').value.trim();
  if (!text) return;
  try {
    const coords = {x: state.pendingNote.x, y: state.pendingNote.y};
    if (state.pendingNote.x2 != null && state.pendingNote.y2 != null) {
      coords.x2 = state.pendingNote.x2;
      coords.y2 = state.pendingNote.y2;
    }
    if (state.pendingNote.noteId) {
      await updateNote(state.pendingNote.noteId, Object.assign({note_text: text}, coords));
    } else {
      await createNote(state.currentPhotoId, Object.assign({note_text: text}, coords));
    }
  } catch (e) { setStatus('Note save failed: ' + e.message); return; }
  noteCancel();
  loadNotes();
}

export async function noteDelete() {
  if (!state.pendingNote || !state.pendingNote.noteId) return;
  try {
    await deleteNote(state.pendingNote.noteId);
  } catch (e) { setStatus('Note delete failed: ' + e.message); return; }
  noteCancel();
  loadNotes();
}

export function noteCancel() {
  state.pendingNote = null;
  document.getElementById('note-panel').classList.add('hidden');
  document.getElementById('note-text').value = '';
  document.getElementById('rect-preview').style.display = 'none';
  renderPins();
}
