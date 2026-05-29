import { state } from './state.js';
import { getPhotos, updatePhoto } from './api.js';
import { setStatus, formatDate, orientedUrl } from './utils.js';
import { tlInit } from './timelapse.js';

const FILTER_IDS = ['start', 'end', 'filter-source', 'filter-photo-type', 'filter-location', 'filter-unit', 'filter-label'];

function updateFilterIndicator() {
  const active = FILTER_IDS.some(id => document.getElementById(id)?.value);
  document.getElementById('clear-filter-btn')?.classList.toggle('active', active);
  document.querySelector('.filters')?.classList.toggle('filtered', active);
}

export async function loadPhotos() {
  const start    = document.getElementById('start').value;
  const end      = document.getElementById('end').value;
  const source   = document.getElementById('filter-source').value;
  const ptype    = document.getElementById('filter-photo-type').value;
  const location = document.getElementById('filter-location').value;
  const unit     = document.getElementById('filter-unit').value;
  const label    = document.getElementById('filter-label')?.value || '';

  updateFilterIndicator();
  setStatus('Loading…');
  try {
    state.allPhotos = await getPhotos({
      start:    start    ? new Date(start + 'T00:00:00').toISOString() : null,
      end:      end      ? new Date(end   + 'T23:59:59').toISOString() : null,
      source, ptype, location, unit, label,
    });
    renderGrid(state.allPhotos);
    const total = state.allPhotos.length;
    const unclassified = state.allPhotos.filter(p => !p.photo_type || !(p.growing_unit_ids && p.growing_unit_ids.length)).length;
    const base = total === 0 ? 'No photos found.' : total + ' photo' + (total === 1 ? '' : 's');
    setStatus(unclassified > 0 ? base + ' · ' + unclassified + ' unclassified' : base);
  } catch (e) {
    setStatus('Error loading photos: ' + e.message);
  }
}

FILTER_IDS.forEach(id => {
  document.getElementById(id)?.addEventListener('change', loadPhotos);
});

function renderGrid(photos) {
  tlInit();
  const grid = document.getElementById('photo-grid');
  grid.innerHTML = '';
  for (let i = 0; i < photos.length; i++) {
    const p = photos[i];
    const isA = state.photoA && state.photoA.id === p.id;
    const isB = state.photoB && state.photoB.id === p.id;
    const card = document.createElement('div');
    card.className = 'photo-card';
    card.dataset.id = p.id;
    const ts = formatDate(p.captured_at);
    const unitNames = (p.growing_unit_ids || [])
      .map(id => { const u = state.allUnits.find(u => u.id === id); return u ? u.name : null; })
      .filter(Boolean).join(', ');
    const caption = unitNames ? ts + ' · ' + unitNames : ts;
    // Grid thumbnails use the rotation-baked variant (not CSS rotation) so dragging a
    // thumbnail into a browser tab opens it in the correct orientation.
    card.innerHTML =
      '<img src="' + orientedUrl(p) + '" alt="' + p.filename + '" loading="lazy" onclick="openModal(' + i + ')">' +
      '<div class="card-ab">' +
        '<button class="sel-a' + (isA ? ' active' : '') + '" onclick="selectA(event,' + i + ')">A</button>' +
        '<button class="sel-b' + (isB ? ' active' : '') + '" onclick="selectB(event,' + i + ')">B</button>' +
      '</div>' +
      '<div class="card-rot">' +
        '<button onclick="gridRotate(event,' + p.id + ',-90)">↺</button>' +
        '<button onclick="gridRotate(event,' + p.id + ',90)">↻</button>' +
      '</div>' +
      '<div class="caption">' + caption + '</div>';
    grid.appendChild(card);
  }
}

export function toggleComparePanel() {
  const body  = document.getElementById('compare-body');
  const label = document.getElementById('compare-toggle-label');
  const open  = body.classList.toggle('open');
  label.textContent = open ? '▾ collapse' : '▸ expand';
}

export function applyFilter() { loadPhotos(); }
export function clearFilter() {
  document.getElementById('start').value = '';
  document.getElementById('end').value   = '';
  document.getElementById('filter-source').value     = '';
  document.getElementById('filter-photo-type').value = '';
  document.getElementById('filter-location').value   = '';
  document.getElementById('filter-unit').value       = '';
  const labelEl = document.getElementById('filter-label');
  if (labelEl) labelEl.value = '';
  loadPhotos();
}

// ── A/B selection ────────────────────────────────────────

export function selectA(e, idx) {
  e.stopPropagation();
  state.photoA = state.allPhotos[idx];
  updateCompare();
  renderGrid(state.allPhotos);
}

export function selectB(e, idx) {
  e.stopPropagation();
  state.photoB = state.allPhotos[idx];
  updateCompare();
  renderGrid(state.allPhotos);
}

function updateCompare() {
  const body  = document.getElementById('compare-body');
  const label = document.getElementById('compare-toggle-label');
  if (body && !body.classList.contains('open')) {
    body.classList.add('open');
    if (label) label.textContent = '▾ collapse';
  }

  const ready = state.photoA && state.photoB;

  if (state.photoA) {
    document.getElementById('slot-a-empty').style.display = 'none';
    const img = document.getElementById('img-a');
    img.src = state.photoA.url;
    img.style.display = 'block';
    img.style.transform = 'rotate(' + (state.photoA.rotation || 0) + 'deg)';
    document.getElementById('cap-a').textContent = formatDate(state.photoA.captured_at);
  }

  if (state.photoB) {
    document.getElementById('slot-b-empty').style.display = 'none';
    const img = document.getElementById('img-b');
    img.src = state.photoB.url;
    img.style.display = 'block';
    img.style.transform = 'rotate(' + (state.photoB.rotation || 0) + 'deg)';
    document.getElementById('cap-b').textContent = formatDate(state.photoB.captured_at);
  }

  document.getElementById('btn-toggle').disabled = !ready;
  document.getElementById('btn-auto').disabled   = !ready;
  updateFlickerFps();
}

// ── Flicker ──────────────────────────────────────────────

export function flickerToggle() {
  stopAuto();
  toggleFlickerFrame();
  showFlickerView();
}

function toggleFlickerFrame() {
  if (!state.photoA || !state.photoB) return;
  state.flickerShowing = state.flickerShowing === 'a' ? 'b' : 'a';
  const photo = state.flickerShowing === 'a' ? state.photoA : state.photoB;
  const flickerImg = document.getElementById('flicker-img');
  flickerImg.src = photo.url;
  flickerImg.style.transform = 'rotate(' + (photo.rotation || 0) + 'deg)';
  const lbl = document.getElementById('flicker-label');
  lbl.textContent = state.flickerShowing.toUpperCase();
  lbl.className = 'flicker-label ' + state.flickerShowing;
}

function showFlickerView() {
  if (!document.getElementById('flicker-view').classList.contains('visible')) {
    state.flickerShowing = 'b'; // toggleFlickerFrame will flip to 'a' first
    toggleFlickerFrame();
    document.getElementById('flicker-view').classList.add('visible');
  }
}

export function flickerAuto() {
  if (state.flickerTimer) {
    stopAuto();
    return;
  }
  showFlickerView();
  const fps = flickerFps();
  state.flickerTimer = setInterval(toggleFlickerFrame, 1000 / fps);
  document.getElementById('btn-auto').classList.add('active');
  document.getElementById('btn-auto').textContent = 'Stop';
}

export function stopAuto() {
  if (state.flickerTimer) { clearInterval(state.flickerTimer); state.flickerTimer = null; }
  document.getElementById('btn-auto').classList.remove('active');
  document.getElementById('btn-auto').textContent = 'Auto flicker';
}

export async function gridRotate(e, photoId, delta) {
  e.stopPropagation();
  const photo = state.allPhotos.find(p => p.id === photoId);
  if (!photo) return;
  const oldRot = photo.rotation || 0;
  const newRot = (oldRot + delta + 360) % 360;
  photo.rotation = newRot;
  // Re-point the thumbnail at the re-oriented variant in-place (no full grid re-render).
  const card = document.querySelector('.photo-card[data-id="' + photoId + '"]');
  let img = null;
  if (card) {
    img = card.querySelector('img');
    if (img) img.src = orientedUrl(photo);
  }
  try {
    await updatePhoto(photoId, {rotation: newRot});
  } catch(err) {
    console.warn('gridRotate failed', err);
    photo.rotation = oldRot;
    if (img) img.src = orientedUrl(photo);
  }
}

function flickerFps() {
  return parseInt(document.getElementById('flicker-speed').value, 10);
}

function updateFlickerFps() {
  const fps = flickerFps();
  document.getElementById('flicker-fps').textContent = fps + ' fps';
}

document.getElementById('flicker-speed').addEventListener('input', function() {
  updateFlickerFps();
  if (state.flickerTimer) { stopAuto(); flickerAuto(); }
});

updateFlickerFps();
