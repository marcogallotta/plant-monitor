import { state } from './state.js';
import {
  getLocations, getGrowingUnits, getPhotos,
  updatePhoto, createEvent,
} from './api.js';
import {
  initSdImport,
  toggleSdPanel, handleSdFolderInput,
  sdSelectAllVisible, sdDeselectAll, sdLoadMore, sdUploadSelected,
} from './sdImport.js';
import {
  initEvents,
  toggleManagePanel, createLocation, createUnit,
  toggleEventsPanel, logEvent,
} from './events.js';
import {
  initNotes,
  loadNotes, renderPins, modalImgClick,
  openCreateForm, noteSave, noteDelete, noteCancel,
} from './notes.js';
import { setStatus, populateSelect } from './utils.js';
import { tlInit, tlPlayPause, tlPrev, tlNext } from './timelapse.js';
import { initUpload, toggleUploadPanel, submitManualUpload } from './upload.js';

  // ── Bootstrap: load locations + units for dropdowns ───────

  async function loadDropdownData() {
    [state.allLocations, state.allUnits] = await Promise.all([
      getLocations(),
      getGrowingUnits(),
    ]);
    populateSelect('filter-location', state.allLocations, 'All locations');
    populateSelect('filter-unit',     state.allUnits,     'All units');
    populateSelect('upload-location', state.allLocations, '— none —');
    populateSelect('upload-units',    state.allUnits,     null);
    populateSelect('id-location-select',  state.allLocations, '— none —');
    populateSelect('id-units-select',     state.allUnits,     null);
    populateSelect('new-event-location',  state.allLocations, '— none —');
    populateSelect('new-event-units',     state.allUnits,     null);
  }

  // ── Timeline ──────────────────────────────────────────────

  async function loadPhotos() {
    const start    = document.getElementById('start').value;
    const end      = document.getElementById('end').value;
    const source   = document.getElementById('filter-source').value;
    const ptype    = document.getElementById('filter-photo-type').value;
    const location = document.getElementById('filter-location').value;
    const unit     = document.getElementById('filter-unit').value;

    setStatus('Loading…');
    try {
      state.allPhotos = await getPhotos({
        start:    start    ? new Date(start).toISOString() : null,
        end:      end      ? new Date(end).toISOString()   : null,
        source, ptype, location, unit,
      });
      renderGrid(state.allPhotos);
      setStatus(state.allPhotos.length === 0 ? 'No photos found.' : state.allPhotos.length + ' photo' + (state.allPhotos.length === 1 ? '' : 's'));
    } catch (e) {
      setStatus('Error loading photos: ' + e.message);
    }
  }

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
      const ts = new Date(p.captured_at).toLocaleString();
      const needsScale = p.rotation === 90 || p.rotation === 270;
      const rotStyle = p.rotation ? ' style="transform:rotate(' + p.rotation + 'deg)' + (needsScale ? ' scale(1.778)' : '') + '"' : '';
      card.innerHTML =
        '<img src="' + p.url + '" alt="' + p.filename + '" loading="lazy" onclick="openModal(' + i + ')"' + rotStyle + '>' +
        '<div class="card-ab">' +
          '<button class="sel-a' + (isA ? ' active' : '') + '" onclick="selectA(event,' + i + ')">A</button>' +
          '<button class="sel-b' + (isB ? ' active' : '') + '" onclick="selectB(event,' + i + ')">B</button>' +
        '</div>' +
        '<div class="caption">' + ts + '</div>';
      grid.appendChild(card);
    }
  }

  function applyFilter() { loadPhotos(); }
  function clearFilter() {
    document.getElementById('start').value = '';
    document.getElementById('end').value   = '';
    document.getElementById('filter-source').value     = '';
    document.getElementById('filter-photo-type').value = '';
    document.getElementById('filter-location').value   = '';
    document.getElementById('filter-unit').value       = '';
    loadPhotos();
  }

  // ── A/B selection ────────────────────────────────────────

  function selectA(e, idx) {
    e.stopPropagation();
    state.photoA = state.allPhotos[idx];
    updateCompare();
    renderGrid(state.allPhotos);
  }

  function selectB(e, idx) {
    e.stopPropagation();
    state.photoB = state.allPhotos[idx];
    updateCompare();
    renderGrid(state.allPhotos);
  }

  function updateCompare() {
    const ready = state.photoA && state.photoB;

    // Slot A
    if (state.photoA) {
      document.getElementById('slot-a-empty').style.display = 'none';
      const img = document.getElementById('img-a');
      img.src = state.photoA.url;
      img.style.display = 'block';
      document.getElementById('cap-a').textContent = new Date(state.photoA.captured_at).toLocaleString();
    }

    // Slot B
    if (state.photoB) {
      document.getElementById('slot-b-empty').style.display = 'none';
      const img = document.getElementById('img-b');
      img.src = state.photoB.url;
      img.style.display = 'block';
      document.getElementById('cap-b').textContent = new Date(state.photoB.captured_at).toLocaleString();
    }

    document.getElementById('btn-toggle').disabled = !ready;
    document.getElementById('btn-auto').disabled   = !ready;
    updateFlickerFps();
  }

  // ── Flicker ──────────────────────────────────────────────

  function flickerToggle() {
    stopAuto();
    toggleFlickerFrame();
    showFlickerView();
  }

  function toggleFlickerFrame() {
    if (!state.photoA || !state.photoB) return;
    state.flickerShowing = state.flickerShowing === 'a' ? 'b' : 'a';
    const photo = state.flickerShowing === 'a' ? state.photoA : state.photoB;
    document.getElementById('flicker-img').src = photo.url;
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

  function flickerAuto() {
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

  function stopAuto() {
    if (state.flickerTimer) { clearInterval(state.flickerTimer); state.flickerTimer = null; }
    document.getElementById('btn-auto').classList.remove('active');
    document.getElementById('btn-auto').textContent = 'Auto flicker';
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

  // ── Modal ────────────────────────────────────────────────

  // ── Zoom / pan / rect draw ───────────────────────────────

  function applyTransform() {
    document.getElementById('modal-img-wrap').style.transform =
      'translate(' + state.panX + 'px, ' + state.panY + 'px) scale(' + state.zoom + ') rotate(' + state.currentRotation + 'deg)';
  }

  function visualToStored(rx, ry) {
    var x, y;
    if (state.currentRotation === 90)       { x = ry;     y = 1 - rx; }
    else if (state.currentRotation === 180) { x = 1 - rx; y = 1 - ry; }
    else if (state.currentRotation === 270) { x = 1 - ry; y = rx;     }
    else                              { x = rx;      y = ry;     }
    return {x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y))};
  }

  async function rotatePhoto(delta) {
    state.currentRotation = ((state.currentRotation + delta) % 360 + 360) % 360;
    resetZoom();
    const photo = state.allPhotos[state.currentIndex];
    photo.rotation = state.currentRotation;
    const card = document.querySelector('.photo-card[data-id="' + photo.id + '"]');
    if (card) {
      var img = card.querySelector('img');
      if (img) {
        const needsScale = state.currentRotation === 90 || state.currentRotation === 270;
        img.style.transform = state.currentRotation ? 'rotate(' + state.currentRotation + 'deg)' + (needsScale ? ' scale(1.778)' : '') : '';
      }
    }
    try {
      await updatePhoto(state.currentPhotoId, {rotation: state.currentRotation});
    } catch (e) { setStatus('Rotation save failed: ' + e.message); }
  }

  function resetZoom() {
    state.zoom = 1; state.panX = 0; state.panY = 0;
    state.isDrawingRect = false; state.rectStart = null;
    document.getElementById('rect-preview').style.display = 'none';
    applyTransform();
  }

  function clampPan() {
    const img = document.getElementById('modal-img');
    const W = img.offsetWidth, H = img.offsetHeight;
    // state.panX/state.panY are in screen pixels; image occupies [state.panX, state.panX+state.zoom*W] × [state.panY, state.panY+state.zoom*H]
    state.panX = Math.min(0, Math.max(W  * (1 - state.zoom), state.panX));
    state.panY = Math.min(0, Math.max(H * (1 - state.zoom), state.panY));
  }

  function openModal(index) {
    showModalPhoto(index);
    document.getElementById('modal').classList.remove('hidden');
  }

  function showModalPhoto(index) {
    state.currentIndex = index;
    const p = state.allPhotos[index];
    state.currentRotation = p.rotation || 0;
    resetZoom();
    noteCancel();
    document.getElementById('modal-log-event-panel').style.display = 'none';
    document.getElementById('modal-event-status').textContent = '';
    state.currentPhotoId = p.id;
    document.getElementById('modal-img').src = p.url;
    document.getElementById('modal-caption').textContent =
      new Date(p.captured_at).toLocaleString() + ' — ' + p.filename;
    showIdentityPanel(p);
    loadNotes();
  }

  function closeModal() {
    noteCancel();
    document.getElementById('modal').classList.add('hidden');
    document.getElementById('modal-img').src = '';
    document.getElementById('identity-panel').classList.add('hidden');
    document.getElementById('modal-log-event-panel').style.display = 'none';
    state.currentPhotoId = null;
    state.currentNotes = [];
  }

  function toggleModalLogEvent() {
    var panel = document.getElementById('modal-log-event-panel');
    panel.style.display = panel.style.display === 'none' ? '' : 'none';
    document.getElementById('modal-event-status').textContent = '';
  }

  async function modalLogEvent() {
    if (!state.currentPhotoId) return;
    var type = document.getElementById('modal-event-type').value;
    var note = document.getElementById('modal-event-note').value.trim();
    var status = document.getElementById('modal-event-status');
    var body = {event_type: type, photo_ids: [state.currentPhotoId]};
    if (note) body.note_text = note;
    status.textContent = 'Saving…';
    try {
      await createEvent(body);
      document.getElementById('modal-event-note').value = '';
      status.textContent = 'Logged.';
    } catch (e) { status.textContent = 'Error: ' + e.message; }
  }

  document.addEventListener('keydown', function(e) {
    const modalOpen = !document.getElementById('modal').classList.contains('hidden');
    if (e.key === 'Escape') { closeModal(); stopAuto(); }
    if (modalOpen) {
      if (e.key === 'ArrowRight' && state.currentIndex < state.allPhotos.length - 1) showModalPhoto(state.currentIndex + 1);
      if (e.key === 'ArrowLeft'  && state.currentIndex > 0)                    showModalPhoto(state.currentIndex - 1);
    }
    if (e.key === 'f' || e.key === 'F') flickerToggle();
  });

  // ── Notes — see notes.js ─────────────────────────────────

  // ── Manage locations + units + Events — see events.js ────

  // ── Manual upload — see upload.js ────────────────────────

  // ── Identity panel ───────────────────────────────────────

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

  async function identityUpdate() {
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

  // ── Timelapse — see timelapse.js ─────────────────────────

  // ── Zoom / pan events ────────────────────────────────────

  var zoomViewport = document.getElementById('zoom-viewport');

  zoomViewport.addEventListener('wheel', function(e) {
    e.preventDefault();
    var rect = this.getBoundingClientRect();
    var cx = e.clientX - rect.left;
    var cy = e.clientY - rect.top;
    var factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    var newZoom = Math.min(Math.max(state.zoom * factor, 1), 10);
    // Keep the point under the cursor fixed: cx = state.panX + state.zoom*lx = newPanX + newZoom*lx
    // => newPanX = cx - (newZoom/state.zoom) * (cx - state.panX)
    state.panX = cx - (newZoom / state.zoom) * (cx - state.panX);
    state.panY = cy - (newZoom / state.zoom) * (cy - state.panY);
    state.zoom = newZoom;
    clampPan();
    applyTransform();
  }, { passive: false });

  function imgCoordsFromEvent(e) {
    var r = document.getElementById('modal-img').getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
      y: Math.max(0, Math.min(1, (e.clientY - r.top)  / r.height)),
    };
  }

  zoomViewport.addEventListener('mousedown', function(e) {
    if (e.button !== 0) return;
    if (e.shiftKey) {
      if (!state.currentPhotoId) return;
      state.isDrawingRect = true;
      var rawStart = imgCoordsFromEvent(e);
      state.rectStart = visualToStored(rawStart.x, rawStart.y);
      this.classList.add('drawing');
      e.preventDefault();
      return;
    }
    if (state.zoom <= 1) return;
    state.isPanning = true;
    state.wasDrag = false;
    state.panStart = { x: e.clientX, y: e.clientY, panX: state.panX, panY: state.panY };
    this.classList.add('grabbing');
    e.preventDefault();
  });

  document.addEventListener('mousemove', function(e) {
    if (state.isDrawingRect) {
      var rawCur = imgCoordsFromEvent(e);
      var cur = visualToStored(rawCur.x, rawCur.y);
      var preview = document.getElementById('rect-preview');
      var x1 = Math.min(state.rectStart.x, cur.x), y1 = Math.min(state.rectStart.y, cur.y);
      var x2 = Math.max(state.rectStart.x, cur.x), y2 = Math.max(state.rectStart.y, cur.y);
      preview.style.left   = (x1 * 100) + '%';
      preview.style.top    = (y1 * 100) + '%';
      preview.style.width  = ((x2 - x1) * 100) + '%';
      preview.style.height = ((y2 - y1) * 100) + '%';
      preview.style.display = 'block';
      return;
    }
    if (!state.isPanning) return;
    var dx = e.clientX - state.panStart.x;
    var dy = e.clientY - state.panStart.y;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) state.wasDrag = true;
    // state.panX/state.panY are screen pixels — no /state.zoom needed
    state.panX = state.panStart.panX + dx;
    state.panY = state.panStart.panY + dy;
    clampPan();
    applyTransform();
  });

  document.addEventListener('mouseup', function(e) {
    if (state.isDrawingRect) {
      var rawCur = imgCoordsFromEvent(e);
      var cur = visualToStored(rawCur.x, rawCur.y);
      document.getElementById('rect-preview').style.display = 'none';
      document.getElementById('zoom-viewport').classList.remove('drawing');
      state.isDrawingRect = false;
      var dx = Math.abs(cur.x - state.rectStart.x), dy = Math.abs(cur.y - state.rectStart.y);
      if (dx > 0.01 || dy > 0.01) {
        state.wasDrag = true;
        openCreateForm(state.rectStart.x, state.rectStart.y, cur.x, cur.y);
      }
      state.rectStart = null;
      return;
    }
    if (!state.isPanning) return;
    state.isPanning = false;
    document.getElementById('zoom-viewport').classList.remove('grabbing');
  });

  // ── SD card import — see sdImport.js ─────────────────────

  updateFlickerFps();
  initNotes(visualToStored);
  initUpload(loadPhotos);
  initSdImport(loadPhotos);
  initEvents(loadDropdownData);
  loadDropdownData().then(loadPhotos);

  Object.assign(window, {
    applyFilter, clearFilter,
    openModal, closeModal, modalImgClick,
    selectA, selectB,
    rotatePhoto, toggleModalLogEvent, modalLogEvent,
    flickerToggle, flickerAuto,
    tlPrev, tlPlayPause, tlNext,
    noteSave, noteDelete, noteCancel,
    toggleUploadPanel, submitManualUpload,
    toggleSdPanel, sdSelectAllVisible, sdDeselectAll, sdLoadMore, sdUploadSelected,
    toggleManagePanel, createLocation, createUnit,
    toggleEventsPanel, logEvent,
    handleSdFolderInput,
    identityUpdate,
  });
