import { state } from './state.js';
import { getNotes, createNote, updateNote, deleteNote } from './api.js';
import { setStatus } from './utils.js';

let _visualToStored;

export function initNotes(visualToStored) {
  _visualToStored = visualToStored;
}

function unitName(id) {
  if (id == null) return null;
  const u = (state.allUnits || []).find(function(u) { return u.id === id; });
  return u ? u.name : null;
}

function eventToStored(e) {  // pointer event -> stored-space (rotation/zoom-correct) coordinate
  const r = document.getElementById('modal-img').getBoundingClientRect();
  return _visualToStored((e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
}

// Drag a region note to reposition it; clamps so it can't leave the image.
function startRectDrag(note, el, e) {
  const s = eventToStored(e);
  const mnx = Math.min(note.x, note.x2), mny = Math.min(note.y, note.y2);
  const mxx = Math.max(note.x, note.x2), mxy = Math.max(note.y, note.y2);
  let dx = 0, dy = 0, moved = false;
  function move(ev) {
    const c = eventToStored(ev);
    dx = Math.max(-mnx, Math.min(1 - mxx, c.x - s.x)); dy = Math.max(-mny, Math.min(1 - mxy, c.y - s.y));
    if (Math.abs(dx) > 0.005 || Math.abs(dy) > 0.005) moved = true;
    el.style.left = (mnx + dx) * 100 + '%'; el.style.top = (mny + dy) * 100 + '%';
  }
  async function up() {
    document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
    if (!moved) return;
    el._suppressClick = true;
    try { await updateNote(note.id, {x: note.x + dx, y: note.y + dy, x2: note.x2 + dx, y2: note.y2 + dy}); } catch (err) { setStatus('Note move failed: ' + err.message); }
    loadNotes();
  }
  document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
}

// Resize a region note by dragging a corner; the opposite corner stays anchored.
// h.left/h.top say which displayed edges the corner controls. Clamps to a min
// size so the box can't collapse or flip.
function startCornerResize(note, el, h, e) {
  const MIN = 0.02;
  const bx1 = Math.min(note.x, note.x2), by1 = Math.min(note.y, note.y2);
  const bx2 = Math.max(note.x, note.x2), by2 = Math.max(note.y, note.y2);
  let nx1 = bx1, ny1 = by1, nx2 = bx2, ny2 = by2, moved = false;
  function move(ev) {
    const c = eventToStored(ev);
    if (h.left) nx1 = Math.min(c.x, bx2 - MIN); else nx2 = Math.max(c.x, bx1 + MIN);
    if (h.top)  ny1 = Math.min(c.y, by2 - MIN); else ny2 = Math.max(c.y, by1 + MIN);
    moved = true;
    el.style.left = nx1 * 100 + '%'; el.style.top = ny1 * 100 + '%';
    el.style.width = (nx2 - nx1) * 100 + '%'; el.style.height = (ny2 - ny1) * 100 + '%';
  }
  async function up() {
    document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
    if (!moved) return;
    el._suppressClick = true;
    try { await updateNote(note.id, {x: nx1, y: ny1, x2: nx2, y2: ny2}); } catch (err) { setStatus('Note resize failed: ' + err.message); }
    loadNotes();
  }
  document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
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
    const uname = unitName(note.growing_unit_id);
    if (note.x2 != null && note.y2 != null) {
      const x1 = Math.min(note.x, note.x2), y1 = Math.min(note.y, note.y2);
      const x2 = Math.max(note.x, note.x2), y2 = Math.max(note.y, note.y2);
      el.className = 'note-rect';
      el.style.left   = (x1 * 100) + '%';
      el.style.top    = (y1 * 100) + '%';
      el.style.width  = ((x2 - x1) * 100) + '%';
      el.style.height = ((y2 - y1) * 100) + '%';
      if (isSelected(note)) {
        el.classList.add('selected');
        el.style.border = '3px dashed #ff0';
        el.style.background = 'rgba(255,255,0,0.25)';
        el.style.zIndex = '10';
      }
      const label = document.createElement('span');
      label.className = 'note-rect-label';
      label.textContent = uname || (i + 1);
      el.appendChild(label);
      el.addEventListener('mousedown', function(e) {       // shift-drag stays with zoom.js (new region)
        if (e.button !== 0 || e.shiftKey) return;
        e.stopPropagation(); e.preventDefault(); startRectDrag(note, el, e);
      });
      [['tl', true, true], ['tr', false, true], ['bl', true, false], ['br', false, false]].forEach(function(h) {
        const g = document.createElement('div');
        g.className = 'rh rh-' + h[0];
        g.addEventListener('mousedown', function(e) {       // resize beats body-move (stopPropagation)
          if (e.button !== 0 || e.shiftKey) return;
          e.stopPropagation(); e.preventDefault(); startCornerResize(note, el, {left: h[1], top: h[2]}, e);
        });
        el.appendChild(g);
      });
    } else {
      el.className = 'note-pin' + (isSelected(note) ? ' selected' : '');
      el.style.left = (note.x * 100) + '%';
      el.style.top  = (note.y * 100) + '%';
      el.textContent = i + 1;
    }
    el.title = [note.note_text, uname && ('Unit: ' + uname)].filter(Boolean).join('\n');
    el.addEventListener('click', function(e) { e.stopPropagation(); if (el._suppressClick) { el._suppressClick = false; return; } openEditForm(note); });
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
  document.getElementById('note-unit').value = '';
  document.getElementById('note-delete').style.display = 'none';
  document.getElementById('note-panel').classList.remove('hidden');
  document.getElementById('note-text').focus();
  renderPins();
}

function openEditForm(note) {
  state.pendingNote = {noteId: note.id, x: note.x, y: note.y, x2: note.x2, y2: note.y2};
  document.getElementById('note-panel-title').textContent = 'Edit note';
  document.getElementById('note-text').value = note.note_text || '';
  document.getElementById('note-unit').value = note.growing_unit_id != null ? String(note.growing_unit_id) : '';
  document.getElementById('note-delete').style.display = 'inline-block';
  document.getElementById('note-panel').classList.remove('hidden');
  document.getElementById('note-text').focus();
  renderPins();
}

export async function noteSave() {
  if (!state.pendingNote || !state.currentPhotoId) return;
  const text = document.getElementById('note-text').value.trim();
  const unitRaw = document.getElementById('note-unit').value;
  const unitId = unitRaw ? Number(unitRaw) : null;
  if (!text && unitId == null) { setStatus('Add a note or pick a growing unit'); return; }
  try {
    const coords = {x: state.pendingNote.x, y: state.pendingNote.y};
    if (state.pendingNote.x2 != null && state.pendingNote.y2 != null) {
      coords.x2 = state.pendingNote.x2;
      coords.y2 = state.pendingNote.y2;
    }
    // growing_unit_id is always sent (null clears it). On edit, note_text is
    // also always sent so emptying the field actually clears it (null); the
    // "text or unit required" rule still blocks clearing both. On create there
    // is no existing text, so an empty field is simply omitted.
    const body = Object.assign({growing_unit_id: unitId}, coords);
    if (state.pendingNote.noteId) {
      body.note_text = text || null;
      await updateNote(state.pendingNote.noteId, body);
    } else {
      if (text) body.note_text = text;
      await createNote(state.currentPhotoId, body);
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
  document.getElementById('note-unit').value = '';
  document.getElementById('rect-preview').style.display = 'none';
  renderPins();
}
