import { state } from './state.js';
import { assignLabel, removeLabel, createLabel } from './api.js';

export function renderLabelSection(photo) {
  const container = document.getElementById('label-assigned');
  if (!container) return;
  container.innerHTML = '';
  (photo.labels || []).forEach(function(label) {
    const chip = document.createElement('span');
    chip.className = 'label-chip active';
    chip.dataset.labelId = label.id;
    const text = document.createTextNode(label.name.replace(/_/g, ' '));
    const btn = document.createElement('button');
    btn.textContent = '×';
    btn.className = 'label-chip-remove';
    btn.onclick = function() { removeAssignedLabel(label.id); };
    chip.appendChild(text);
    chip.appendChild(btn);
    container.appendChild(chip);
  });
  const input = document.getElementById('label-input');
  if (input) { input.value = ''; }
  const dropdown = document.getElementById('label-dropdown');
  if (dropdown) { dropdown.classList.add('hidden'); dropdown.innerHTML = ''; }
}

export function handleLabelInput() {
  const input = document.getElementById('label-input');
  const dropdown = document.getElementById('label-dropdown');
  if (!input || !dropdown) return;
  const query = input.value.trim().toLowerCase();
  if (!query) { dropdown.classList.add('hidden'); dropdown.innerHTML = ''; return; }
  const photo = state.allPhotos[state.currentIndex];
  const assignedIds = new Set((photo ? photo.labels || [] : []).map(function(l) { return l.id; }));
  const normalized = query.replace(/\s+/g, '_');
  const matches = (state.allLabels || []).filter(function(l) {
    return l.name.includes(normalized) && !assignedIds.has(l.id);
  });
  dropdown.innerHTML = '';
  matches.forEach(function(label) {
    const item = document.createElement('div');
    item.className = 'label-dropdown-item';
    item.textContent = label.name.replace(/_/g, ' ');
    item.onmousedown = function() { selectExistingLabel(label.id); };
    dropdown.appendChild(item);
  });
  const exactMatch = (state.allLabels || []).some(function(l) { return l.name === normalized; });
  if (!exactMatch) {
    const createItem = document.createElement('div');
    createItem.className = 'label-dropdown-item label-create';
    createItem.textContent = 'Create label "' + query + '"';
    createItem.onmousedown = function() { createAndAssignLabel(query); };
    dropdown.appendChild(createItem);
  }
  dropdown.classList.toggle('hidden', dropdown.children.length === 0);
}

export async function handleLabelKeydown(e) {
  if (e.key !== 'Enter') return;
  e.preventDefault();
  const input = document.getElementById('label-input');
  if (!input) return;
  const query = input.value.trim().toLowerCase();
  if (!query) return;
  const normalized = query.replace(/\s+/g, '_');
  const existing = (state.allLabels || []).find(function(l) { return l.name === normalized; });
  if (existing) {
    await selectExistingLabel(existing.id);
  } else {
    await createAndAssignLabel(query);
  }
}

async function selectExistingLabel(labelId) {
  if (!state.currentPhotoId) return;
  const photo = state.allPhotos[state.currentIndex];
  if ((photo.labels || []).some(function(l) { return l.id === labelId; })) return;
  const status = document.getElementById('label-status');
  try {
    const updated = await assignLabel(state.currentPhotoId, labelId);
    state.allPhotos[state.currentIndex] = updated;
    renderLabelSection(updated);
    if (status) status.textContent = '';
  } catch (e) {
    if (status) status.textContent = 'Error';
  }
}

async function createAndAssignLabel(name) {
  if (!state.currentPhotoId) return;
  const status = document.getElementById('label-status');
  try {
    const label = await createLabel(name);
    if (!(state.allLabels || []).some(function(l) { return l.id === label.id; })) {
      state.allLabels.push(label);
    }
    const updated = await assignLabel(state.currentPhotoId, label.id);
    state.allPhotos[state.currentIndex] = updated;
    renderLabelSection(updated);
    if (status) status.textContent = '';
  } catch (e) {
    if (status) status.textContent = 'Error: ' + e.message;
  }
}

async function removeAssignedLabel(labelId) {
  if (!state.currentPhotoId) return;
  const status = document.getElementById('label-status');
  try {
    await removeLabel(state.currentPhotoId, labelId);
    const photo = state.allPhotos[state.currentIndex];
    const updated = Object.assign({}, photo, {
      labels: (photo.labels || []).filter(function(l) { return l.id !== labelId; }),
    });
    state.allPhotos[state.currentIndex] = updated;
    renderLabelSection(updated);
    if (status) status.textContent = '';
  } catch (e) {
    if (status) status.textContent = 'Error';
  }
}
