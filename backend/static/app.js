import { state } from './state.js';
import { getLocations, getGrowingUnits } from './api.js';
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
import { populateSelect } from './utils.js';
import { tlPrev, tlPlayPause, tlNext } from './timelapse.js';
import { initUpload, toggleUploadPanel, submitManualUpload } from './upload.js';
import { visualToStored } from './zoom.js';
import {
  openModal, closeModal, showModalPhoto,
  rotatePhoto, toggleModalLogEvent, modalLogEvent,
  identityUpdate,
} from './modal.js';
import {
  loadPhotos,
  applyFilter, clearFilter,
  selectA, selectB,
  flickerToggle, flickerAuto, stopAuto,
} from './photos.js';

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

document.addEventListener('keydown', function(e) {
  const modalOpen = !document.getElementById('modal').classList.contains('hidden');
  if (e.key === 'Escape') { closeModal(); stopAuto(); }
  if (modalOpen) {
    if (e.key === 'ArrowRight' && state.currentIndex < state.allPhotos.length - 1) showModalPhoto(state.currentIndex + 1);
    if (e.key === 'ArrowLeft'  && state.currentIndex > 0)                    showModalPhoto(state.currentIndex - 1);
  }
  if (e.key === 'f' || e.key === 'F') flickerToggle();
});

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
