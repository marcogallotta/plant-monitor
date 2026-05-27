import { state } from './state.js';
import { getLocations, getGrowingUnits, getPhotos } from './api.js';
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
import { initNotes, modalImgClick, noteSave, noteDelete, noteCancel } from './notes.js';
import { setStatus, populateSelect } from './utils.js';
import { tlInit, tlPlayPause, tlPrev, tlNext } from './timelapse.js';
import { initUpload, toggleUploadPanel, submitManualUpload } from './upload.js';
import { visualToStored } from './zoom.js';
import {
  openModal, closeModal, showModalPhoto,
  rotatePhoto, toggleModalLogEvent, modalLogEvent,
  identityUpdate,
} from './modal.js';

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

  // ── Modal — see modal.js ─────────────────────────────────

  document.addEventListener('keydown', function(e) {
    const modalOpen = !document.getElementById('modal').classList.contains('hidden');
    if (e.key === 'Escape') { closeModal(); stopAuto(); }
    if (modalOpen) {
      if (e.key === 'ArrowRight' && state.currentIndex < state.allPhotos.length - 1) showModalPhoto(state.currentIndex + 1);
      if (e.key === 'ArrowLeft'  && state.currentIndex > 0)                    showModalPhoto(state.currentIndex - 1);
    }
    if (e.key === 'f' || e.key === 'F') flickerToggle();
  });

  // ── Timelapse — see timelapse.js ─────────────────────────

  // ── Zoom / pan — see zoom.js ─────────────────────────────

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
