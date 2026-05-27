import { createEvent, getEvents, createLocation as apiCreateLocation, createGrowingUnit } from './api.js';

let _reloadDropdowns = null;

export function initEvents(reloadDropdowns) {
  _reloadDropdowns = reloadDropdowns;
}

// ── Manage locations + units ──────────────────────────────

export function toggleManagePanel() {
  const form = document.getElementById('manage-form');
  const label = document.getElementById('manage-toggle-label');
  const open = form.classList.toggle('open');
  label.textContent = open ? '▾ collapse' : '▸ expand';
}

export async function createLocation() {
  const name = document.getElementById('new-loc-name').value.trim();
  if (!name) { document.getElementById('loc-status').textContent = 'Name required.'; return; }
  const desc = document.getElementById('new-loc-desc').value.trim();
  try {
    await apiCreateLocation({name: name, description: desc || null});
    document.getElementById('new-loc-name').value = '';
    document.getElementById('new-loc-desc').value = '';
    document.getElementById('loc-status').textContent = 'Added.';
    if (_reloadDropdowns) await _reloadDropdowns();
  } catch (e) { document.getElementById('loc-status').textContent = 'Error: ' + e.message; }
}

export async function createUnit() {
  const name = document.getElementById('new-unit-name').value.trim();
  if (!name) { document.getElementById('unit-status').textContent = 'Name required.'; return; }
  const type = document.getElementById('new-unit-type').value;
  try {
    await createGrowingUnit({name: name, unit_type: type || null});
    document.getElementById('new-unit-name').value = '';
    document.getElementById('new-unit-type').value = '';
    document.getElementById('unit-status').textContent = 'Added.';
    if (_reloadDropdowns) await _reloadDropdowns();
  } catch (e) { document.getElementById('unit-status').textContent = 'Error: ' + e.message; }
}

// ── Events ────────────────────────────────────────────────

export function toggleEventsPanel() {
  const form = document.getElementById('events-form');
  const label = document.getElementById('events-toggle-label');
  const open = form.classList.toggle('open');
  label.textContent = open ? '▾ collapse' : '▸ expand';
  if (open) loadEvents();
}

export async function logEvent() {
  const type = document.getElementById('new-event-type').value;
  const at   = document.getElementById('new-event-at').value;
  const loc  = document.getElementById('new-event-location').value;
  const unitSel = document.getElementById('new-event-units');
  const note = document.getElementById('new-event-note').value.trim();

  const body = {event_type: type};
  if (at)   body.event_at    = new Date(at).toISOString();
  if (loc)  body.location_id = parseInt(loc);
  const unitIds = Array.from(unitSel.selectedOptions).map(o => parseInt(o.value));
  if (unitIds.length) body.growing_unit_ids = unitIds;
  if (note) body.note_text = note;

  document.getElementById('event-status').textContent = 'Saving…';
  try {
    await createEvent(body);
    document.getElementById('new-event-at').value = '';
    document.getElementById('new-event-location').value = '';
    Array.from(unitSel.options).forEach(o => { o.selected = false; });
    document.getElementById('new-event-note').value = '';
    document.getElementById('event-status').textContent = 'Logged.';
    loadEvents();
  } catch (e) { document.getElementById('event-status').textContent = 'Error: ' + e.message; }
}

async function loadEvents() {
  try {
    const events = await getEvents();
    const list = document.getElementById('event-list');
    if (!events.length) { list.textContent = 'No events yet.'; return; }
    list.innerHTML = '';
    events.forEach(function(ev) {
      const row = document.createElement('div');
      row.style.cssText = 'padding:0.35rem 0.5rem;background:#1a1a1a;border-radius:3px;border-left:3px solid #444;';

      const typeSpan = document.createElement('span');
      typeSpan.style.cssText = 'color:#8af;font-weight:600;';
      typeSpan.textContent = ev.event_type.replace(/_/g, ' ');
      row.appendChild(typeSpan);

      const metaSpan = document.createElement('span');
      metaSpan.style.cssText = 'color:#555;margin-left:0.5rem;';
      metaSpan.textContent = new Date(ev.event_at).toLocaleString() + (ev.location_name ? ' @ ' + ev.location_name : '');
      row.appendChild(metaSpan);

      const units = ev.growing_units.map(u => u.name).join(', ');
      if (units) {
        const unitsDiv = document.createElement('div');
        unitsDiv.style.cssText = 'color:#888;margin-top:0.15rem;';
        unitsDiv.textContent = units;
        row.appendChild(unitsDiv);
      }

      if (ev.note_text) {
        const noteDiv = document.createElement('div');
        noteDiv.style.cssText = 'color:#aaa;margin-top:0.15rem;font-style:italic;';
        noteDiv.textContent = ev.note_text;
        row.appendChild(noteDiv);
      }

      list.appendChild(row);
    });
  } catch (e) { /* silent */ }
}
