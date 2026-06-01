import { state } from './state.js';
import { getPhotos, updatePhoto, deletePhoto } from './api.js';
import { setStatus, formatDate, orientedUrl } from './utils.js';
import { tlInit } from './timelapse.js';

const FILTER_IDS = ['start', 'end', 'filter-source', 'filter-photo-type', 'filter-location'];
const _rawPageSize = parseInt(new URLSearchParams(window.location.search).get('page_size') || '60', 10);
const PAGE_SIZE = Number.isFinite(_rawPageSize) ? Math.min(Math.max(_rawPageSize, 1), 500) : 60;
let currentOffset = 0;
let lastFilterParams = {};
let activeUnitId  = '';
let activeLabelId = '';
let selectMode = false;
const selectedIds = new Set();

// Restore chip state from hash immediately so renderQuickChips() picks it up correctly.
{
  const _p = new URLSearchParams(window.location.hash.slice(1));
  activeUnitId  = _p.get('unit')  || '';
  activeLabelId = _p.get('label') || '';
}

function writeFiltersToHash() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const start    = document.getElementById('start').value;
  const end      = document.getElementById('end').value;
  const source   = document.getElementById('filter-source').value;
  const ptype    = document.getElementById('filter-photo-type').value;
  const loc      = document.getElementById('filter-location').value;
  start    ? params.set('start', start)    : params.delete('start');
  end      ? params.set('end', end)        : params.delete('end');
  source   ? params.set('source', source)  : params.delete('source');
  ptype    ? params.set('ptype', ptype)    : params.delete('ptype');
  loc      ? params.set('location', loc)   : params.delete('location');
  activeUnitId  ? params.set('unit', activeUnitId)   : params.delete('unit');
  activeLabelId ? params.set('label', activeLabelId) : params.delete('label');
  const str = params.toString();
  history.replaceState(null, '', str ? '#' + str : window.location.pathname + window.location.search);
}

export function readFiltersFromHash() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const el = id => document.getElementById(id);
  if (params.has('start'))    el('start').value             = params.get('start');
  if (params.has('end'))      el('end').value               = params.get('end');
  if (params.has('source'))   el('filter-source').value     = params.get('source');
  if (params.has('ptype'))    el('filter-photo-type').value = params.get('ptype');
  if (params.has('location')) el('filter-location').value   = params.get('location');
  activeUnitId  = params.get('unit')  || '';
  activeLabelId = params.get('label') || '';
}

function updateFilterIndicator() {
  const active = FILTER_IDS.some(id => document.getElementById(id)?.value) || !!activeUnitId || !!activeLabelId;
  document.getElementById('clear-filter-btn')?.classList.toggle('active', active);
  document.querySelector('.filters')?.classList.toggle('filtered', active);
}

export async function loadPhotos() {
  const start    = document.getElementById('start').value;
  const end      = document.getElementById('end').value;
  const source   = document.getElementById('filter-source').value;
  const ptype    = document.getElementById('filter-photo-type').value;
  const location = document.getElementById('filter-location').value;
  const unit     = activeUnitId;
  const label    = activeLabelId;

  updateFilterIndicator();
  setStatus('Loading…');
  try {
    lastFilterParams = {
      start:    start    ? new Date(start + 'T00:00:00').toISOString() : null,
      end:      end      ? new Date(end   + 'T23:59:59').toISOString() : null,
      source, ptype, location, unit, label,
    };
    currentOffset = 0;
    const result = await getPhotos({...lastFilterParams, limit: PAGE_SIZE, offset: 0});
    state.allPhotos = result.photos;
    state.totalPhotos = result.total;
    renderGrid();
    const loaded = state.allPhotos.length;
    const total = state.totalPhotos;
    const paginated = loaded < total;
    const unclassified = paginated ? 0 : state.allPhotos.filter(p => !p.photo_type || !(p.growing_unit_ids && p.growing_unit_ids.length)).length;
    const base = total === 0 ? 'No photos found.' : (paginated ? 'Showing ' + loaded + ' of ' + total : total + ' photo' + (total === 1 ? '' : 's'));
    setStatus(unclassified > 0 ? base + ' · ' + unclassified + ' unclassified' : base);
    writeFiltersToHash();
  } catch (e) {
    setStatus('Error loading photos: ' + e.message);
  }
}

FILTER_IDS.forEach(id => {
  document.getElementById(id)?.addEventListener('change', loadPhotos);
});

function buildCard(p, i) {
  const isA = state.photoA && state.photoA.id === p.id;
  const isB = state.photoB && state.photoB.id === p.id;
  const card = document.createElement('div');
  card.className = 'photo-card' + (selectedIds.has(p.id) ? ' selected' : '');
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
    '<button class="card-del" onclick="gridDelete(event,' + p.id + ')" title="Delete photo">🗑</button>' +
    '<div class="caption">' + caption + '</div>';
  return card;
}

function renderGrid() {
  tlInit();
  selectedIds.clear();
  if (selectMode) _updateSelectBar();
  const grid = document.getElementById('photo-grid');
  grid.innerHTML = '';
  const photos = state.allPhotos;
  for (let i = 0; i < photos.length; i++) {
    grid.appendChild(buildCard(photos[i], i));
  }
  _appendLoadMoreRow(grid);
}

function _appendLoadMoreRow(grid) {
  if (state.allPhotos.length < state.totalPhotos) {
    const remaining = state.totalPhotos - state.allPhotos.length;
    const row = document.createElement('div');
    row.className = 'load-more-row';
    row.innerHTML = '<button onclick="loadMorePhotos()" class="load-more-btn">' +
      'Load more (' + remaining + ' remaining)</button>';
    grid.appendChild(row);
  }
}

export async function loadMorePhotos() {
  const startIdx = state.allPhotos.length;
  currentOffset = startIdx;
  try {
    const result = await getPhotos({...lastFilterParams, limit: PAGE_SIZE, offset: currentOffset});
    state.totalPhotos = result.total;
    state.allPhotos = [...state.allPhotos, ...result.photos];
    const grid = document.getElementById('photo-grid');
    grid.querySelector('.load-more-row')?.remove();
    for (let i = startIdx; i < state.allPhotos.length; i++) {
      grid.appendChild(buildCard(state.allPhotos[i], i));
    }
    _appendLoadMoreRow(grid);
    const loaded = state.allPhotos.length;
    const total = state.totalPhotos;
    const paginated = loaded < total;
    const unclassified = paginated ? 0 : state.allPhotos.filter(p => !p.photo_type || !(p.growing_unit_ids && p.growing_unit_ids.length)).length;
    const base = paginated ? 'Showing ' + loaded + ' of ' + total : total + ' photo' + (total === 1 ? '' : 's');
    setStatus(unclassified > 0 ? base + ' · ' + unclassified + ' unclassified' : base);
  } catch (e) {
    setStatus('Error loading more: ' + e.message);
  }
}

export function applyFilter() { loadPhotos(); }
export function clearFilter() {
  document.getElementById('start').value = '';
  document.getElementById('end').value   = '';
  document.getElementById('filter-source').value     = '';
  document.getElementById('filter-photo-type').value = '';
  document.getElementById('filter-location').value   = '';
  activeUnitId  = '';
  activeLabelId = '';
  renderQuickChips();
  loadPhotos();
}

function quickChipClick(type, id) {
  if (type === 'unit') {
    activeUnitId  = activeUnitId  === id ? '' : id;
  } else {
    activeLabelId = activeLabelId === id ? '' : id;
  }
  renderQuickChips();
  loadPhotos();
}

export function renderQuickChips() {
  const container = document.getElementById('quick-chips');
  if (!container) return;
  container.innerHTML = '';
  const units  = state.allUnits  || [];
  const labels = state.allLabels || [];
  for (const u of units) {
    const btn = document.createElement('button');
    btn.className = 'qchip' + (activeUnitId === String(u.id) ? ' active' : '');
    btn.textContent = u.name;
    btn.addEventListener('click', () => quickChipClick('unit', String(u.id)));
    container.appendChild(btn);
  }
  if (units.length && labels.length) {
    const sep = document.createElement('span');
    sep.className = 'qchip-sep';
    container.appendChild(sep);
  }
  for (const l of labels) {
    const btn = document.createElement('button');
    btn.className = 'qchip' + (activeLabelId === String(l.id) ? ' active' : '');
    btn.textContent = l.name;
    btn.addEventListener('click', () => quickChipClick('label', String(l.id)));
    container.appendChild(btn);
  }
}

// ── A/B selection ────────────────────────────────────────

export function selectA(e, idx) {
  e.stopPropagation();
  state.photoA = state.allPhotos[idx];
  updateCompare();
  renderGrid();
}

export function selectB(e, idx) {
  e.stopPropagation();
  state.photoB = state.allPhotos[idx];
  updateCompare();
  renderGrid();
}

function updateCompare() {
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

export async function gridDelete(e, photoId) {
  e.stopPropagation();
  if (!confirm('Delete this photo? This cannot be undone.')) return;
  try {
    await deletePhoto(photoId);
    state.allPhotos = state.allPhotos.filter(p => p.id !== photoId);
    state.totalPhotos = Math.max(0, (state.totalPhotos || 0) - 1);
    if (state.photoA?.id === photoId) { state.photoA = null; updateCompare(); stopAuto(); }
    if (state.photoB?.id === photoId) { state.photoB = null; updateCompare(); stopAuto(); }
    renderGrid();
    const total = state.totalPhotos;
    setStatus(total === 0 ? 'No photos found.' : total + ' photo' + (total === 1 ? '' : 's'));
  } catch(err) {
    alert('Delete failed: ' + err.message);
  }
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

// ── Mass select / delete ─────────────────────────────────

// Capture-phase listener intercepts card clicks before the img's inline
// onclick fires, so select mode doesn't accidentally open the modal.
document.getElementById('photo-grid').addEventListener('click', function(e) {
  if (!selectMode) return;
  const card = e.target.closest('.photo-card');
  if (!card) return;
  e.stopPropagation();
  e.preventDefault();
  const id = parseInt(card.dataset.id, 10);
  if (selectedIds.has(id)) {
    selectedIds.delete(id);
    card.classList.remove('selected');
  } else {
    selectedIds.add(id);
    card.classList.add('selected');
  }
  _updateSelectBar();
}, true);

function _updateSelectBar() {
  const n = selectedIds.size;
  const count = document.getElementById('select-count');
  if (count) count.textContent = n + ' selected';
  for (const id of ['delete-selected-btn', 'download-selected-btn', 'copy-sheet-btn']) {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = n === 0;
  }
}

export function toggleSelectMode() {
  selectMode = !selectMode;
  selectedIds.clear();
  document.querySelectorAll('.photo-card.selected').forEach(c => c.classList.remove('selected'));
  document.getElementById('photo-grid').classList.toggle('select-mode', selectMode);
  document.getElementById('select-mode-btn').classList.toggle('active', selectMode);
  document.getElementById('select-bar').classList.toggle('hidden', !selectMode);
  _updateSelectBar();
}

export function selectAll() {
  if (!selectMode) return;
  state.allPhotos.forEach(p => {
    if (!selectedIds.has(p.id)) {
      selectedIds.add(p.id);
      document.querySelector('.photo-card[data-id="' + p.id + '"]')?.classList.add('selected');
    }
  });
  _updateSelectBar();
}

export async function copySheet() {
  const photos = [...selectedIds].map(id => state.allPhotos.find(p => p.id === id)).filter(Boolean);
  if (!photos.length) return;

  const btn = document.getElementById('copy-sheet-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Building…'; }

  const CELL = 1024;   // max px per side per photo
  const COLS = 2;
  const PAD  = 12;
  const LABEL_H = 36;
  const FONT = 'bold 18px sans-serif';

  // Load and resize each photo into an ImageBitmap
  const cells = await Promise.all(photos.map(async photo => {
    const resp = await fetch(orientedUrl(photo));
    const blob = await resp.blob();
    const bmp  = await createImageBitmap(blob);
    const scale = Math.min(1, CELL / Math.max(bmp.width, bmp.height));
    const w = Math.round(bmp.width  * scale);
    const h = Math.round(bmp.height * scale);
    const unitNames = (photo.growing_unit_ids || [])
      .map(id => { const u = state.allUnits.find(u => u.id === id); return u ? u.name : null; })
      .filter(Boolean).join(', ');
    const label = (unitNames || '—') + '  ·  ' + formatDate(photo.captured_at);
    return { bmp, w, h, label };
  }));

  const rows = Math.ceil(cells.length / COLS);
  const colW = CELL + PAD * 2;
  const rowH = CELL + LABEL_H + PAD * 2;
  const canvas = document.createElement('canvas');
  canvas.width  = COLS * colW;
  canvas.height = rows * rowH;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  cells.forEach(({ bmp, w, h, label }, i) => {
    const col = i % COLS;
    const row = Math.floor(i / COLS);
    const x = col * colW + PAD + Math.round((CELL - w) / 2);
    const y = row * rowH + PAD + Math.round((CELL - h) / 2);
    ctx.drawImage(bmp, x, y, w, h);
    bmp.close();

    // Label bar below the image
    const lx = col * colW;
    const ly = row * rowH + PAD + CELL;
    ctx.fillStyle = '#222';
    ctx.fillRect(lx, ly, colW, LABEL_H);
    ctx.fillStyle = '#ddd';
    ctx.font = FONT;
    ctx.textBaseline = 'middle';
    ctx.fillText(label, lx + PAD, ly + LABEL_H / 2, colW - PAD * 2);
  });

  const pngBlob = await new Promise(res => canvas.toBlob(res, 'image/png'));
  await navigator.clipboard.write([new ClipboardItem({ 'image/png': pngBlob })]);

  if (btn) { btn.disabled = false; btn.textContent = 'Copy sheet'; }
  setStatus('Copied contact sheet (' + photos.length + ' photo' + (photos.length === 1 ? '' : 's') + ') — paste into ChatGPT or anywhere.');
}

export function downloadSelected() {
  if (!selectedIds.size) return;
  const a = document.createElement('a');
  a.href = '/photos/export?ids=' + [...selectedIds].join(',');
  a.download = 'photos.zip';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export async function deleteSelected() {
  const ids = [...selectedIds];
  if (!ids.length) return;
  if (!confirm('Delete ' + ids.length + ' photo' + (ids.length === 1 ? '' : 's') + '? This cannot be undone.')) return;
  const results = await Promise.allSettled(ids.map(id => deletePhoto(id)));
  let failed = 0;
  results.forEach((r, i) => {
    const id = ids[i];
    if (r.status === 'fulfilled') {
      state.allPhotos = state.allPhotos.filter(p => p.id !== id);
      state.totalPhotos = Math.max(0, (state.totalPhotos || 0) - 1);
      if (state.photoA?.id === id) { state.photoA = null; updateCompare(); stopAuto(); }
      if (state.photoB?.id === id) { state.photoB = null; updateCompare(); stopAuto(); }
      document.querySelector('.photo-card[data-id="' + id + '"]')?.remove();
    } else {
      failed++;
    }
  });
  selectMode = false;
  selectedIds.clear();
  document.getElementById('photo-grid').classList.remove('select-mode');
  document.getElementById('select-mode-btn').classList.remove('active');
  document.getElementById('select-bar').classList.add('hidden');
  const total = state.totalPhotos;
  const base = total === 0 ? 'No photos found.' : total + ' photo' + (total === 1 ? '' : 's');
  setStatus(failed ? base + ' · ' + failed + ' deletion' + (failed === 1 ? '' : 's') + ' failed' : base);
}
