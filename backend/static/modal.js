import { state } from './state.js';
import { updatePhoto, createEvent } from './api.js';
import { renderLabelSection } from './labels.js';
import { resetZoom } from './zoom.js';
import { noteCancel, loadNotes } from './notes.js';
import { setStatus, formatDate, rotTransform } from './utils.js';

export async function rotatePhoto(delta) {
  state.currentRotation = ((state.currentRotation + delta) % 360 + 360) % 360;
  resetZoom();
  const photo = state.allPhotos[state.currentIndex];
  photo.rotation = state.currentRotation;
  const card = document.querySelector('.photo-card[data-id="' + photo.id + '"]');
  if (card) {
    var img = card.querySelector('img');
    if (img) img.style.transform = rotTransform(state.currentRotation);
  }
  try {
    await updatePhoto(state.currentPhotoId, {rotation: state.currentRotation});
  } catch (e) { setStatus('Rotation save failed: ' + e.message); }
}

export function openModal(index) {
  showModalPhoto(index);
  document.getElementById('modal').classList.remove('hidden');
}

export function showModalPhoto(index) {
  state.currentIndex = index;
  const p = state.allPhotos[index];
  state.currentRotation = p.rotation || 0;
  resetZoom();
  noteCancel();
  state.currentPhotoId = p.id;
  document.getElementById('modal-img').src = p.url;
  document.getElementById('modal-caption').textContent =
    formatDate(p.captured_at) + ' — ' + p.filename;
  showIdentityPanel(p);
  renderLabelSection(p);
  loadNotes();
  document.getElementById('modal-event-panel').classList.add('hidden');
  document.getElementById('modal-event-type').selectedIndex = 0;
  document.getElementById('modal-event-note').value = '';
  document.getElementById('modal-event-status').textContent = '';
}

export function closeModal() {
  noteCancel();
  document.getElementById('modal').classList.add('hidden');
  document.getElementById('modal-img').src = '';
  document.getElementById('identity-panel').classList.add('hidden');
  state.currentPhotoId = null;
  state.currentNotes = [];
}


function showIdentityPanel(photo) {
  document.getElementById('identity-panel').classList.remove('hidden');
  document.getElementById('id-source').textContent = photo.source || '—';

  const typeSelect = document.getElementById('id-type-select');
  typeSelect.value = photo.photo_type || '';

  const locSelect = document.getElementById('id-location-select');
  locSelect.value = photo.location_id || '';

  const unitSelect = document.getElementById('id-units-select');
  const selectedIds = new Set((photo.growing_units || []).map(function(u) { return String(u.id); }));
  Array.from(unitSelect.options).forEach(function(o) { o.selected = selectedIds.has(o.value); });

  const origRow = document.getElementById('id-original-row');
  if (photo.original_filename) {
    origRow.style.display = 'flex';
    document.getElementById('id-original').textContent = photo.original_filename;
  } else {
    origRow.style.display = 'none';
  }
}

export function toggleModalLogEvent() {
  const panel = document.getElementById('modal-event-panel');
  panel.classList.toggle('hidden');
  if (!panel.classList.contains('hidden')) {
    document.getElementById('modal-event-status').textContent = '';
  }
}

export async function logModalEvent() {
  if (!state.currentPhotoId) return;
  const type = document.getElementById('modal-event-type').value;
  const note = document.getElementById('modal-event-note').value.trim();
  const status = document.getElementById('modal-event-status');
  if (!type) { status.textContent = 'Select a type.'; return; }
  const body = {event_type: type, photo_ids: [state.currentPhotoId]};
  if (note) body.note_text = note;
  try {
    await createEvent(body);
    document.getElementById('modal-event-type').selectedIndex = 0;
    document.getElementById('modal-event-note').value = '';
    document.getElementById('modal-event-panel').classList.add('hidden');
    status.textContent = 'Logged.';
  } catch (e) { status.textContent = 'Error: ' + e.message; }
}

export async function identityUpdate() {
  if (!state.currentPhotoId) return;
  const typeSelect = document.getElementById('id-type-select');
  const locSelect  = document.getElementById('id-location-select');
  const unitSelect = document.getElementById('id-units-select');
  const body = {
    photo_type:       typeSelect.value || null,
    location_id:      locSelect.value  ? parseInt(locSelect.value) : null,
    growing_unit_ids: Array.from(unitSelect.selectedOptions).map(function(o) { return parseInt(o.value); }),
  };
  try {
    const updated = await updatePhoto(state.currentPhotoId, body);
    const idx = state.allPhotos.findIndex(function(p) { return p.id === state.currentPhotoId; });
    if (idx !== -1) state.allPhotos[idx] = updated;
    showIdentityPanel(updated);
    setStatus('Saved.');
  } catch (e) { setStatus('Identity update failed: ' + e.message); }
}
