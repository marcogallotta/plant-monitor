import { state } from './state.js';
import { getLocations, getGrowingUnits, getLabels } from './api.js';
import {
  initSdImport,
  toggleSdPanel, handleSdFolderInput, handleSdScan,
  sdSelectAllVisible, sdDeselectAll, sdLoadMore, sdUploadSelected,
  sdAddGroup, sdAddMore,
} from './sdImport.js';
import {
  initEvents,
  toggleManagePanel, createLocation, createUnit,
  toggleEventsPanel, logEvent,
} from './events.js';
import { initNotes, modalImgClick, noteSave, noteDelete, noteCancel } from './notes.js';
import { populateSelect } from './utils.js';
import { tlPrev, tlPlayPause, tlNext, toggleTlPanel } from './timelapse.js';
import { initUpload, toggleUploadPanel, submitManualUpload } from './upload.js';
import { visualToStored } from './zoom.js';
import {
  openModal, closeModal, showModalPhoto,
  rotatePhoto,
  identityUpdate,
  toggleModalLogEvent, logModalEvent,
} from './modal.js';
import { handleLabelInput, handleLabelKeydown } from './labels.js';
import { loadSensorStrip } from './sensors.js';
import {
  loadPhotos,
  applyFilter, clearFilter,
  selectA, selectB,
  flickerToggle, flickerAuto, stopAuto,
  gridRotate,
  toggleComparePanel,
  loadMorePhotos,
} from './photos.js';

async function loadDropdownData() {
  [state.allLocations, state.allUnits, state.allLabels] = await Promise.all([
    getLocations(),
    getGrowingUnits(),
    getLabels(),
  ]);
  populateSelect('filter-location', state.allLocations, 'All locations');
  populateSelect('filter-unit',     state.allUnits,     'All units');
  populateSelect('filter-label',    state.allLabels,    'All labels');
  populateSelect('upload-location', state.allLocations, '— none —');
  populateSelect('upload-units',    state.allUnits,     null);
  populateSelect('id-location-select',  state.allLocations, '— none —');
  populateSelect('id-units-select',     state.allUnits,     null);
  populateSelect('new-event-location',  state.allLocations, '— none —');
  populateSelect('new-event-units',     state.allUnits,     null);
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
  if (e.key === 'f' || e.key === 'F') flickerToggle();
});

initNotes(visualToStored);
initUpload(loadPhotos);
initSdImport(loadPhotos);
initEvents(loadDropdownData);
loadDropdownData().then(loadPhotos);
loadSensorStrip();

Object.assign(window, {
  applyFilter, clearFilter, loadMorePhotos,
  openModal, closeModal, modalImgClick,
  modalPrev, modalNext,
  selectA, selectB,
  rotatePhoto, gridRotate,
  handleLabelInput, handleLabelKeydown,
  flickerToggle, flickerAuto,
  toggleComparePanel,
  tlPrev, tlPlayPause, tlNext, toggleTlPanel,
  noteSave, noteDelete, noteCancel,
  toggleUploadPanel, submitManualUpload,
  toggleSdPanel, sdSelectAllVisible, sdDeselectAll, sdLoadMore, sdUploadSelected,
  toggleManagePanel, createLocation, createUnit,
  toggleEventsPanel, logEvent,
  handleSdFolderInput, handleSdScan, sdAddGroup, sdAddMore,
  identityUpdate,
  toggleModalLogEvent, logModalEvent,
});
