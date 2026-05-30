import { uploadPhoto } from './api.js';

let _loadPhotos;

export function initUpload(loadPhotos) {
  _loadPhotos = loadPhotos;
}

export async function submitManualUpload() {
  const fileInput = document.getElementById('upload-image');
  if (!fileInput.files.length) {
    document.getElementById('upload-status').textContent = 'Choose an image first.';
    return;
  }
  const fd = new FormData();
  fd.append('image', fileInput.files[0]);
  const capturedAt = document.getElementById('upload-captured-at').value;
  if (capturedAt) fd.append('captured_at', new Date(capturedAt).toISOString());
  const ptype = document.getElementById('upload-photo-type').value;
  if (ptype) fd.append('photo_type', ptype);
  const loc = document.getElementById('upload-location').value;
  if (loc) fd.append('location_id', loc);
  const unitSel = document.getElementById('upload-units');
  Array.from(unitSel.selectedOptions).forEach(function(o) { fd.append('growing_unit_ids', o.value); });
  const note = document.getElementById('upload-note').value.trim();
  if (note) fd.append('note_text', note);

  document.getElementById('upload-status').textContent = 'Uploading…';
  try {
    await uploadPhoto(fd);
    document.getElementById('upload-status').textContent = 'Uploaded.';
    fileInput.value = '';
    document.getElementById('upload-captured-at').value  = '';
    document.getElementById('upload-photo-type').value   = '';
    document.getElementById('upload-location').value     = '';
    Array.from(document.getElementById('upload-units').options).forEach(function(o) { o.selected = false; });
    document.getElementById('upload-note').value = '';
    _loadPhotos();
  } catch (e) {
    document.getElementById('upload-status').textContent = 'Error: ' + e.message;
  }
}
