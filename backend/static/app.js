import { state } from './state.js';
import { getLocations, getGrowingUnits, getLabels } from './api.js';
import {
  initSdImport,
  handleSdFolderInput, handleSdScan,
  sdSelectAllVisible, sdDeselectAll, sdLoadMore, sdUploadSelected,
  sdAddGroup, sdAddMore,
} from './sdImport.js';
import {
  initEvents,
  createLocation, createUnit,
  logEvent,
} from './events.js';
import { initNotes, modalImgClick, noteSave, noteDelete, noteCancel } from './notes.js';
import { populateSelect } from './utils.js';
import { tlPrev, tlPlayPause, tlNext } from './timelapse.js';
import { initUpload, submitManualUpload } from './upload.js';
import { visualToStored } from './zoom.js';
import {
  openModal, closeModal, showModalPhoto, openModalForPhoto,
  rotatePhoto,
  identityUpdate,
  toggleModalLogEvent, logModalEvent,
} from './modal.js';
import { handleLabelInput, handleLabelKeydown } from './labels.js';
import { loadSensorStrip } from './sensors.js';
import { initReview, reviewFocus, reviewResolve, reviewKeydown, reviewOpenPhoto, reviewEdit, reviewEditCancel, reviewAcceptEdited, reviewChoose } from './review.js';
import {
  loadPhotos,
  applyFilter, clearFilter,
  selectA, selectB,
  flickerToggle, flickerAuto, stopAuto,
  gridRotate, gridDelete,
  loadMorePhotos,
  renderQuickChips,
  readFiltersFromHash,
  toggleSelectMode, selectAll, deleteSelected, downloadSelected, copySheet,
  batchSetType, batchSetLocation, batchAddUnit, batchAddLabel,
} from './photos.js';

async function loadDropdownData() {
  [state.allLocations, state.allUnits, state.allLabels] = await Promise.all([
    getLocations(),
    getGrowingUnits(),
    getLabels(),
  ]);
  populateSelect('filter-location', state.allLocations, 'All locations');
  readFiltersFromHash();
  renderQuickChips();
  populateSelect('upload-location', state.allLocations, '— none —');
  populateSelect('upload-units',    state.allUnits,     null);
  populateSelect('id-location-select',  state.allLocations, '— none —');
  populateSelect('id-units-select',     state.allUnits,     null);
  populateSelect('new-event-location',  state.allLocations, '— none —');
  populateSelect('new-event-units',     state.allUnits,     null);
  populateSelect('note-unit',           state.allUnits,     '— no unit —');
  populateBatchSelects();
}

// Batch select-bar dropdowns keep a non-selectable placeholder (and a "clear"
// option for location), so they can't go through populateSelect which wipes the
// first option. Each is repopulated from scratch keeping its leading options.
function populateBatchSelects() {
  const appendOptions = (id, items) => {
    const sel = document.getElementById(id);
    if (!sel) return;
    sel.querySelectorAll('option[data-dynamic]').forEach(o => o.remove());
    const tail = sel.querySelector('option[data-tail]');
    items.forEach(item => {
      const opt = document.createElement('option');
      opt.value = item.id;
      opt.textContent = item.name;
      opt.dataset.dynamic = '1';
      sel.insertBefore(opt, tail);
    });
  };
  appendOptions('batch-location-select', state.allLocations);
  appendOptions('batch-unit-select',     state.allUnits);
  appendOptions('batch-label-select',    state.allLabels);
}

function modalPrev() {
  if (state.currentIndex > 0) showModalPhoto(state.currentIndex - 1);
}

function modalNext() {
  if (state.currentIndex < state.allPhotos.length - 1) showModalPhoto(state.currentIndex + 1);
}

document.addEventListener('keydown', function(e) {
  const modalOpen = !document.getElementById('modal').classList.contains('hidden');
  if (e.key === 'Escape') { closeModal(); stopAuto(); }
  if (modalOpen) {
    if (e.key === 'ArrowRight') modalNext();
    if (e.key === 'ArrowLeft')  modalPrev();
  }
  if ((e.key === 'f' || e.key === 'F') && document.getElementById('tab-gallery')?.classList.contains('active')) flickerToggle();
  reviewKeydown(e);
});

let reviewLoaded = false;
function switchTab(name) {
  if (!document.getElementById('tab-' + name)) name = 'gallery';
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.querySelector(`.tab-btn[data-tab="${name}"]`)?.classList.add('active');
  const params = new URLSearchParams(window.location.hash.slice(1));
  params.set('tab', name);
  history.replaceState(null, '', '#' + params.toString());
  if (name === 'review' && !reviewLoaded) { reviewLoaded = true; initReview(); }
}

initNotes(visualToStored);
initUpload(loadPhotos);
initSdImport(loadPhotos);
initEvents(loadDropdownData);
loadDropdownData().then(loadPhotos);
loadSensorStrip();
switchTab(new URLSearchParams(window.location.hash.slice(1)).get('tab') || localStorage.getItem('activeTab') || 'gallery');

Object.assign(window, {
  applyFilter, clearFilter, loadMorePhotos,
  openModal, closeModal, openModalForPhoto, modalImgClick,
  modalPrev, modalNext,
  selectA, selectB,
  rotatePhoto, gridRotate, gridDelete,
  handleLabelInput, handleLabelKeydown,
  flickerToggle, flickerAuto,
  tlPrev, tlPlayPause, tlNext,
  noteSave, noteDelete, noteCancel,
  submitManualUpload,
  sdSelectAllVisible, sdDeselectAll, sdLoadMore, sdUploadSelected,
  createLocation, createUnit,
  logEvent,
  handleSdFolderInput, handleSdScan, sdAddGroup, sdAddMore,
  identityUpdate,
  toggleModalLogEvent, logModalEvent,
  switchTab,
  toggleSelectMode, selectAll, deleteSelected, downloadSelected, copySheet,
  batchSetType, batchSetLocation, batchAddUnit, batchAddLabel,
  initReview, reviewFocus, reviewResolve, reviewOpenPhoto, reviewEdit, reviewEditCancel, reviewAcceptEdited, reviewChoose,
});
