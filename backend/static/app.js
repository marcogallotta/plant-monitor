import { state } from './state.js';

  // ── Bootstrap: load locations + units for dropdowns ───────

  async function loadDropdownData() {
    const [locResp, unitResp] = await Promise.all([
      fetch('/locations'),
      fetch('/growing-units'),
    ]);
    state.allLocations = locResp.ok ? await locResp.json() : [];
    state.allUnits     = unitResp.ok ? await unitResp.json() : [];
    populateSelect('filter-location', state.allLocations, 'All locations');
    populateSelect('filter-unit',     state.allUnits,     'All units');
    populateSelect('upload-location', state.allLocations, '— none —');
    populateSelect('upload-units',    state.allUnits,     null);
    populateSelect('id-location-select',  state.allLocations, '— none —');
    populateSelect('id-units-select',     state.allUnits,     null);
    populateSelect('new-event-location',  state.allLocations, '— none —');
    populateSelect('new-event-units',     state.allUnits,     null);
  }

  function populateSelect(id, items, blankLabel) {
    const sel = document.getElementById(id);
    const multiple = sel.multiple;
    if (!multiple) {
      sel.innerHTML = blankLabel ? '<option value="">' + blankLabel + '</option>' : '';
    } else {
      sel.innerHTML = '';
    }
    items.forEach(function(item) {
      const opt = document.createElement('option');
      opt.value = item.id;
      opt.textContent = item.name;
      sel.appendChild(opt);
    });
  }

  // ── Timeline ──────────────────────────────────────────────

  async function loadPhotos() {
    const start    = document.getElementById('start').value;
    const end      = document.getElementById('end').value;
    const source   = document.getElementById('filter-source').value;
    const ptype    = document.getElementById('filter-photo-type').value;
    const location = document.getElementById('filter-location').value;
    const unit     = document.getElementById('filter-unit').value;
    let url = '/photos';
    const p = [];
    if (start)    p.push('start='          + encodeURIComponent(new Date(start).toISOString()));
    if (end)      p.push('end='            + encodeURIComponent(new Date(end).toISOString()));
    if (source)   p.push('source='         + encodeURIComponent(source));
    if (ptype)    p.push('photo_type='     + encodeURIComponent(ptype));
    if (location) p.push('location_id='   + encodeURIComponent(location));
    if (unit)     p.push('growing_unit_id=' + encodeURIComponent(unit));
    if (p.length) url += '?' + p.join('&');

    setStatus('Loading…');
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      state.allPhotos = await resp.json();
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
  function setStatus(msg) { document.getElementById('status').textContent = msg; }

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
      await fetch('/photos/' + state.currentPhotoId, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({rotation: state.currentRotation}),
      });
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
      var resp = await fetch('/events', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        var err = await resp.json().catch(function() { return {}; });
        throw new Error(err.detail || 'HTTP ' + resp.status);
      }
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

  // ── Notes ─────────────────────────────────────────────────

  async function loadNotes() {
    if (!state.currentPhotoId) return;
    try {
      const resp = await fetch('/photos/' + state.currentPhotoId + '/notes');
      if (!resp.ok) return;
      state.currentNotes = await resp.json();
      renderPins();
    } catch (e) { setStatus('Failed to load notes: ' + e.message); }
  }

  function renderPins() {
    const container = document.getElementById('note-pins');
    container.innerHTML = '';
    const isSelected = function(note) { return state.pendingNote && state.pendingNote.noteId === note.id; };
    state.currentNotes.forEach(function(note, i) {
      const el = document.createElement('div');
      if (note.x2 != null && note.y2 != null) {
        const x1 = Math.min(note.x, note.x2), y1 = Math.min(note.y, note.y2);
        const x2 = Math.max(note.x, note.x2), y2 = Math.max(note.y, note.y2);
        el.className = 'note-rect';
        el.style.left   = (x1 * 100) + '%';
        el.style.top    = (y1 * 100) + '%';
        el.style.width  = ((x2 - x1) * 100) + '%';
        el.style.height = ((y2 - y1) * 100) + '%';
        if (isSelected(note)) {
          el.style.border = '3px dashed #ff0';
          el.style.background = 'rgba(255,255,0,0.25)';
          el.style.zIndex = '10';
        }
        const label = document.createElement('span');
        label.className = 'note-rect-label';
        label.textContent = i + 1;
        el.appendChild(label);
      } else {
        el.className = 'note-pin' + (isSelected(note) ? ' selected' : '');
        el.style.left = (note.x * 100) + '%';
        el.style.top  = (note.y * 100) + '%';
        el.textContent = i + 1;
      }
      el.title = note.note_text;
      el.addEventListener('click', function(e) { e.stopPropagation(); openEditForm(note); });
      container.appendChild(el);
    });
  }

  function modalImgClick(e) {
    if (state.wasDrag) { state.wasDrag = false; return; }
    if (!state.currentPhotoId) return;
    const img = document.getElementById('modal-img');
    const r = img.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) return;
    const raw = visualToStored(
      (e.clientX - r.left) / r.width,
      (e.clientY - r.top)  / r.height
    );
    openCreateForm(raw.x, raw.y);
  }

  function openCreateForm(x, y, x2, y2) {
    state.pendingNote = {x: x, y: y, x2: x2 != null ? x2 : null, y2: y2 != null ? y2 : null};
    var isRect = x2 != null && y2 != null;
    document.getElementById('note-panel-title').textContent = isRect ? 'New region note' : 'New note';
    document.getElementById('note-text').value = '';
    document.getElementById('note-delete').style.display = 'none';
    document.getElementById('note-panel').classList.remove('hidden');
    document.getElementById('note-text').focus();
    renderPins();
  }

function openEditForm(note) {
    state.pendingNote = {noteId: note.id, x: note.x, y: note.y, x2: note.x2, y2: note.y2};
    document.getElementById('note-panel-title').textContent = 'Edit note';
    document.getElementById('note-text').value = note.note_text;
    document.getElementById('note-delete').style.display = 'inline-block';
    document.getElementById('note-panel').classList.remove('hidden');
    document.getElementById('note-text').focus();
    renderPins();
  }

  async function noteSave() {
    if (!state.pendingNote || !state.currentPhotoId) return;
    const text = document.getElementById('note-text').value.trim();
    if (!text) return;
    try {
      const coords = {x: state.pendingNote.x, y: state.pendingNote.y};
      if (state.pendingNote.x2 != null && state.pendingNote.y2 != null) {
        coords.x2 = state.pendingNote.x2;
        coords.y2 = state.pendingNote.y2;
      }
      if (state.pendingNote.noteId) {
        await fetch('/notes/' + state.pendingNote.noteId, {
          method: 'PUT',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(Object.assign({note_text: text}, coords)),
        });
      } else {
        await fetch('/photos/' + state.currentPhotoId + '/notes', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(Object.assign({note_text: text}, coords)),
        });
      }
    } catch (e) { setStatus('Note save failed: ' + e.message); return; }
    noteCancel();
    loadNotes();
  }

  async function noteDelete() {
    if (!state.pendingNote || !state.pendingNote.noteId) return;
    try {
      await fetch('/notes/' + state.pendingNote.noteId, {method: 'DELETE'});
    } catch (e) { setStatus('Note delete failed: ' + e.message); return; }
    noteCancel();
    loadNotes();
  }

  function noteCancel() {
    state.pendingNote = null;
    document.getElementById('note-panel').classList.add('hidden');
    document.getElementById('note-text').value = '';
    document.getElementById('rect-preview').style.display = 'none';
    renderPins();
  }

  // ── Manage locations + units ─────────────────────────────

  function toggleManagePanel() {
    const form = document.getElementById('manage-form');
    const label = document.getElementById('manage-toggle-label');
    const open = form.classList.toggle('open');
    label.textContent = open ? '▾ collapse' : '▸ expand';
  }

  async function createLocation() {
    const name = document.getElementById('new-loc-name').value.trim();
    if (!name) { document.getElementById('loc-status').textContent = 'Name required.'; return; }
    const desc = document.getElementById('new-loc-desc').value.trim();
    try {
      const resp = await fetch('/locations', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name, description: desc || null}),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(function() { return {}; });
        throw new Error(err.detail || 'HTTP ' + resp.status);
      }
      document.getElementById('new-loc-name').value = '';
      document.getElementById('new-loc-desc').value = '';
      document.getElementById('loc-status').textContent = 'Added.';
      await loadDropdownData();
    } catch (e) { document.getElementById('loc-status').textContent = 'Error: ' + e.message; }
  }

  async function createUnit() {
    const name = document.getElementById('new-unit-name').value.trim();
    if (!name) { document.getElementById('unit-status').textContent = 'Name required.'; return; }
    const type = document.getElementById('new-unit-type').value;
    try {
      const resp = await fetch('/growing-units', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name, unit_type: type || null}),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(function() { return {}; });
        throw new Error(err.detail || 'HTTP ' + resp.status);
      }
      document.getElementById('new-unit-name').value = '';
      document.getElementById('new-unit-type').value = '';
      document.getElementById('unit-status').textContent = 'Added.';
      await loadDropdownData();
    } catch (e) { document.getElementById('unit-status').textContent = 'Error: ' + e.message; }
  }

  // ── Events ───────────────────────────────────────────────

  function toggleEventsPanel() {
    const form = document.getElementById('events-form');
    const label = document.getElementById('events-toggle-label');
    const open = form.classList.toggle('open');
    label.textContent = open ? '▾ collapse' : '▸ expand';
    if (open) loadEvents();
  }

  async function logEvent() {
    const type = document.getElementById('new-event-type').value;
    const at   = document.getElementById('new-event-at').value;
    const loc  = document.getElementById('new-event-location').value;
    const unitSel = document.getElementById('new-event-units');
    const note = document.getElementById('new-event-note').value.trim();

    const body = {event_type: type};
    if (at)   body.event_at    = new Date(at).toISOString();
    if (loc)  body.location_id = parseInt(loc);
    const unitIds = Array.from(unitSel.selectedOptions).map(function(o) { return parseInt(o.value); });
    if (unitIds.length) body.growing_unit_ids = unitIds;
    if (note) body.note_text = note;

    document.getElementById('event-status').textContent = 'Saving…';
    try {
      const resp = await fetch('/events', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(function() { return {}; });
        throw new Error(err.detail || 'HTTP ' + resp.status);
      }
      document.getElementById('new-event-at').value = '';
      document.getElementById('new-event-location').value = '';
      Array.from(unitSel.options).forEach(function(o) { o.selected = false; });
      document.getElementById('new-event-note').value = '';
      document.getElementById('event-status').textContent = 'Logged.';
      loadEvents();
    } catch (e) { document.getElementById('event-status').textContent = 'Error: ' + e.message; }
  }

  async function loadEvents() {
    try {
      const resp = await fetch('/events');
      if (!resp.ok) return;
      const events = await resp.json();
      const list = document.getElementById('event-list');
      if (!events.length) { list.textContent = 'No events yet.'; return; }
      list.innerHTML = '';
      events.forEach(function(ev) {
        const row = document.createElement('div');
        row.style.cssText = 'padding:0.35rem 0.5rem;background:#1a1a1a;border-radius:3px;border-left:3px solid #444;';
        const when = new Date(ev.event_at).toLocaleString();

        const typeSpan = document.createElement('span');
        typeSpan.style.cssText = 'color:#8af;font-weight:600;';
        typeSpan.textContent = ev.event_type.replace(/_/g, ' ');
        row.appendChild(typeSpan);

        const metaSpan = document.createElement('span');
        metaSpan.style.cssText = 'color:#555;margin-left:0.5rem;';
        metaSpan.textContent = when + (ev.location_name ? ' @ ' + ev.location_name : '');
        row.appendChild(metaSpan);

        const units = ev.growing_units.map(function(u) { return u.name; }).join(', ');
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

  // ── Manual upload ────────────────────────────────────────

  function toggleUploadPanel() {
    const form = document.getElementById('upload-form');
    const label = document.getElementById('upload-toggle-label');
    const open = form.classList.toggle('open');
    label.textContent = open ? '▾ collapse' : '▸ expand';
  }

  async function submitManualUpload() {
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
      const resp = await fetch('/manual-photos', {method: 'POST', body: fd});
      if (!resp.ok) {
        const err = await resp.json().catch(function() { return {}; });
        throw new Error(err.detail || 'HTTP ' + resp.status);
      }
      document.getElementById('upload-status').textContent = 'Uploaded.';
      fileInput.value = '';
      document.getElementById('upload-captured-at').value  = '';
      document.getElementById('upload-photo-type').value   = '';
      document.getElementById('upload-location').value     = '';
      Array.from(document.getElementById('upload-units').options).forEach(function(o) { o.selected = false; });
      document.getElementById('upload-note').value = '';
      loadPhotos();
    } catch (e) {
      document.getElementById('upload-status').textContent = 'Error: ' + e.message;
    }
  }

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
      const resp = await fetch('/photos/' + state.currentPhotoId, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(function() { return {}; });
        throw new Error(err.detail || 'HTTP ' + resp.status);
      }
      const updated = await resp.json();
      const idx = state.allPhotos.findIndex(function(p) { return p.id === state.currentPhotoId; });
      if (idx !== -1) state.allPhotos[idx] = updated;
      showIdentityPanel(updated);
      setStatus('Saved.');
    } catch (e) { setStatus('Identity update failed: ' + e.message); }
  }

  // ── Timelapse ────────────────────────────────────────────


  function tlInit() {
    tlStop();
    state.tlIndex = 0;
    const empty = document.getElementById('tl-empty');
    const img   = document.getElementById('tl-img');
    const label = document.getElementById('tl-label');
    const hasPhotos = state.allPhotos.length > 0;
    empty.style.display = hasPhotos ? 'none' : 'block';
    img.style.display   = hasPhotos ? 'block' : 'none';
    label.style.display = hasPhotos ? 'block' : 'none';
    document.getElementById('tl-prev').disabled = !hasPhotos;
    document.getElementById('tl-play').disabled = !hasPhotos;
    document.getElementById('tl-next').disabled = !hasPhotos;
    if (hasPhotos) tlShowFrame();
  }

  function tlShowFrame() {
    const p = state.allPhotos[state.tlIndex];
    document.getElementById('tl-img').src = p.url;
    document.getElementById('tl-label').textContent = new Date(p.captured_at).toLocaleString();
    document.getElementById('tl-counter').textContent = (state.tlIndex + 1) + ' / ' + state.allPhotos.length;
  }

  function tlPlayPause() {
    if (state.tlTimer) { tlStop(); return; }
    const btn = document.getElementById('tl-play');
    btn.textContent = '⏸ Pause';
    btn.classList.add('active');
    const fps = parseInt(document.getElementById('tl-speed').value, 10);
    state.tlTimer = setInterval(function() {
      state.tlIndex = (state.tlIndex + 1) % state.allPhotos.length;
      tlShowFrame();
    }, 1000 / fps);
  }

  function tlStop() {
    if (state.tlTimer) { clearInterval(state.tlTimer); state.tlTimer = null; }
    const btn = document.getElementById('tl-play');
    btn.textContent = '▶ Play';
    btn.classList.remove('active');
  }

  function tlPrev() {
    tlStop();
    state.tlIndex = (state.tlIndex - 1 + state.allPhotos.length) % state.allPhotos.length;
    tlShowFrame();
  }

  function tlNext() {
    tlStop();
    state.tlIndex = (state.tlIndex + 1) % state.allPhotos.length;
    tlShowFrame();
  }

  function tlFps() { return parseInt(document.getElementById('tl-speed').value, 10); }

  document.getElementById('tl-speed').addEventListener('input', function() {
    document.getElementById('tl-fps').textContent = tlFps() + ' fps';
    if (state.tlTimer) { tlStop(); tlPlayPause(); }
  });

  document.getElementById('tl-fps').textContent = tlFps() + ' fps';

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

  // ── SD card import ───────────────────────────────────────

  var SD_PAGE = 20;
  // [{file, selected, thumbUrl, uploadFile, isRaw}]
  // thumbUrl/uploadFile are null for ORF until extracted async
  var sdFiles = [];
  var sdShown = 0;

  function toggleSdPanel() {
    var form  = document.getElementById('sd-form');
    var label = document.getElementById('sd-toggle-label');
    var open  = form.classList.toggle('open');
    label.textContent = open ? '▾ collapse' : '▸ expand';
  }

  function handleSdFolderInput(event) {
    var status = document.getElementById('sd-folder-status');

    sdFiles.forEach(function(e) { if (e.thumbUrl) URL.revokeObjectURL(e.thumbUrl); });
    sdFiles = [];
    sdShown = 0;
    document.getElementById('sd-grid-controls').style.display = 'none';
    document.getElementById('sd-load-more-row').style.display = 'none';
    document.getElementById('sd-grid').innerHTML = '';

    var uploaded = new Set(state.allPhotos.map(function(p) { return p.original_filename; }).filter(Boolean));

    var all = Array.from(event.target.files);
    var photos = all.filter(function(f) {
      var lower = f.name.toLowerCase();
      if (!lower.endsWith('.jpg') && !lower.endsWith('.jpeg') && !lower.endsWith('.orf') && !lower.endsWith('.arw')) return false;
      return !uploaded.has(f.name);
    });

    var skipped = all.filter(function(f) {
      var lower = f.name.toLowerCase();
      return (lower.endsWith('.jpg') || lower.endsWith('.jpeg') || lower.endsWith('.orf') || lower.endsWith('.arw')) && uploaded.has(f.name);
    }).length;

    if (photos.length === 0) {
      status.textContent = skipped > 0 ? 'All ' + skipped + ' already imported.' : 'No photos found.';
      return;
    }

    // most recently shot first — sort by filename descending (sequential camera numbering)
    photos.sort(function(a, b) { return b.name.localeCompare(a.name); });

    sdFiles = photos.map(function(f) {
      var lower  = f.name.toLowerCase();
      var isRaw  = lower.endsWith('.orf') || lower.endsWith('.arw');
      return {
        file:        f,
        selected:    false,
        isRaw:       isRaw,
        thumbUrl:    isRaw ? null : URL.createObjectURL(f),
        uploadFile:  isRaw ? null : f,
        capturedAt:  null,  // filled async by sdParseExif
        tsBadge:     null,
        sessionBreak: false,
      };
    });

    // detect session boundary: first time gap > 1 hour between consecutive files
    var SD_TIME_GAP = 60 * 60 * 1000;
    var batchEnd = -1; // -1 = no clear boundary found
    for (var i = 0; i < sdFiles.length - 1; i++) {
      var tA = sdFiles[i].file.lastModified;
      var tB = sdFiles[i+1].file.lastModified;
      if (tA > 0 && tB > 0 && (tA - tB) > SD_TIME_GAP) {
        sdFiles[i+1].sessionBreak = true;
        batchEnd = i + 1;
        break;
      }
    }

    // auto-select only if a clear boundary was found
    if (batchEnd > 0) {
      for (var i = 0; i < batchEnd; i++) sdFiles[i].selected = true;
    }

    var batchLabel  = batchEnd > 0 ? ' — ' + batchEnd + ' in latest batch' : '';
    var skipLabel   = skipped > 0 ? ' (' + skipped + ' already imported)' : '';
    status.textContent = sdFiles.length + ' photo' + (sdFiles.length === 1 ? '' : 's') + batchLabel + skipLabel;
    document.getElementById('sd-grid-controls').style.display = 'flex';
    // load full batch + 3 past the break so the cutoff is visible; else show first page
    sdAppendThumbs(batchEnd > 0 ? batchEnd + 3 : SD_PAGE);
  }

  function sdAppendThumbs(count) {
    var grid = document.getElementById('sd-grid');
    var from = sdShown;
    var end  = Math.min(sdShown + count, sdFiles.length);
    for (var i = from; i < end; i++) {
      if (sdFiles[i].sessionBreak) grid.appendChild(sdMakeSeparator());
      grid.appendChild(sdMakeThumb(i));
    }
    sdShown = end;
    sdUpdateLoadMore();
    sdUpdateCount();
    sdExtractRawThumbs(from, end);
    sdParseExif(from, end);
  }

  function sdMakeSeparator() {
    var div = document.createElement('div');
    div.className   = 'sd-session-break';
    div.textContent = '— older —';
    return div;
  }

  function sdMakeThumb(i) {
    var entry = sdFiles[i];
    var wrap  = document.createElement('div');
    wrap.className   = 'sd-thumb-wrap' + (entry.selected ? ' selected' : '');
    wrap.dataset.idx = i;
    wrap.addEventListener('click', function() { sdToggle(i); });

    var img = document.createElement('img');
    img.alt     = entry.file.name;
    img.loading = 'lazy';
    if (entry.thumbUrl) {
      img.src = entry.thumbUrl;
    } else {
      img.style.display = 'none';
      var lbl = document.createElement('div');
      lbl.className = 'sd-orf-label';
      lbl.id        = 'sd-orf-lbl-' + i;
      lbl.textContent = 'RAW';
      wrap.appendChild(lbl);
    }

    var caption = document.createElement('div');
    caption.className = 'sd-thumb-caption';
    var nameSpan = document.createElement('div');
    nameSpan.textContent = entry.file.name;
    var tsSpan = document.createElement('div');
    tsSpan.className = 'sd-ts-line';
    tsSpan.id        = 'sd-ts-line-' + i;
    if (entry.tsBadge) tsSpan.dataset.badge = entry.tsBadge;
    tsSpan.textContent = entry.capturedAt ? sdFmtTs(entry.capturedAt) : '';
    caption.appendChild(nameSpan);
    caption.appendChild(tsSpan);

    var check = document.createElement('div');
    check.className = 'sd-thumb-check';

    wrap.appendChild(img);
    wrap.appendChild(caption);
    wrap.appendChild(check);
    return wrap;
  }

  // Scan a Uint8Array for the largest complete embedded JPEG (FF D8 FF ... FF D9).
  // Returns {jpeg: Uint8Array, truncated: bool}.
  // truncated=true means a JPEG started but its FFD9 end marker wasn't found —
  // caller should re-scan a larger buffer before trusting the result.
  function scanForJpeg(bytes) {
    var best = null;
    var truncated = false;
    var i = 0;
    while (i < bytes.length - 3) {
      if (bytes[i] === 0xFF && bytes[i+1] === 0xD8 && bytes[i+2] === 0xFF) {
        var j = i + 2;
        var found = false;
        while (j < bytes.length - 1) {
          if (bytes[j] === 0xFF && bytes[j+1] === 0xD9) {
            var size = j + 2 - i;
            if (!best || size > best.size) best = {start: i, size: size};
            i = j + 2;
            found = true;
            break;
          }
          j++;
        }
        if (!found) { truncated = true; break; }
      } else {
        i++;
      }
    }
    var jpeg = best ? bytes.slice(best.start, best.start + best.size) : null;
    return {jpeg: jpeg, truncated: truncated};
  }

  // Extract the largest embedded JPEG from a raw camera file.
  // Try a 768 KB slice first for speed; if a JPEG was cut off (FFD9 not found),
  // fall through to a full read so the complete preview isn't missed.
  async function extractEmbeddedJpeg(file) {
    var isOrf = file.name.toLowerCase().endsWith('.orf');
    if (!isOrf && file.size > 786432) {
      var slice  = file.slice(0, 786432);
      var bytes  = new Uint8Array(await slice.arrayBuffer());
      var result = scanForJpeg(bytes);
      if (result.jpeg && !result.truncated) return result.jpeg;
      // a JPEG was cut off — fall through to full read to get the complete preview
    }
    var bytes = new Uint8Array(await file.arrayBuffer());
    return scanForJpeg(bytes).jpeg;
  }

  async function sdExtractRawThumbs(from, to) {
    for (var i = from; i < to; i++) {
      var entry = sdFiles[i];
      if (!entry.isRaw || entry.thumbUrl) continue;
      try {
        var jpegBytes = await extractEmbeddedJpeg(entry.file);
        if (!jpegBytes) continue;
        var blob = new Blob([jpegBytes], {type: 'image/jpeg'});
        entry.thumbUrl   = URL.createObjectURL(blob);
        // keep raw filename so backend stores original_filename = DSC01349.ARW
        entry.uploadFile = new File([blob], entry.file.name, {type: 'image/jpeg'});
        var wrap = document.querySelector('.sd-thumb-wrap[data-idx="' + i + '"]');
        if (wrap) {
          var img = wrap.querySelector('img');
          if (img) { img.src = entry.thumbUrl; img.style.display = ''; }
          var lbl = document.getElementById('sd-orf-lbl-' + i);
          if (lbl) lbl.remove();
        }
      } catch(e) { console.warn('RAW thumb failed', entry.file.name, e); }
    }
  }

  var SD_TZ = 'Europe/Rome';

  // Format an ISO timestamp for display in the caption (date + time, no seconds).
  function sdFmtTs(iso) {
    try {
      return new Date(iso).toLocaleString('sv-SE', {timeZone: 'Europe/Rome',
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit'}).replace('T', ' ');
    } catch(e) { return iso.slice(0, 16); }
  }

  // Derive captured_at ISO string from EXIF data using the priority chain.
  // Returns {iso, badge} where badge is 'ok' | 'assumed' | 'fallback'.
  //
  // exifr parses DateTimeOriginal into a JS Date. When OffsetTimeOriginal is
  // present exifr applies it, so the Date is already correct UTC — toISOString()
  // is safe. When there is no offset exifr treats the raw values as local browser
  // time, which is good enough given the browser runs in the camera's timezone.
  function sdDeriveTs(exif, file) {
    var dto = exif && (exif.DateTimeOriginal || exif.CreateDate);
    if (dto) {
      var d = dto instanceof Date ? dto : new Date(dto);
      if (!isNaN(d.getTime())) {
        var hasOffset = !!(exif && exif.OffsetTimeOriginal);
        return {iso: d.toISOString(), badge: hasOffset ? 'ok' : 'assumed'};
      }
    }
    return {iso: new Date(file.lastModified).toISOString(), badge: 'fallback'};
  }

  async function sdParseExif(from, to) {
    for (var i = from; i < to; i++) {
      var entry = sdFiles[i];
      if (entry.capturedAt) continue;
      var exif = null;
      try {
        // exifr can read JPEG and ARW; ORF is not supported — will return null
        exif = await exifr.parse(entry.file, ['DateTimeOriginal', 'CreateDate', 'OffsetTimeOriginal']);
      } catch(e) { /* unsupported format — fallback below */ }
      var result      = sdDeriveTs(exif, entry.file);
      entry.capturedAt = result.iso;
      entry.tsBadge    = result.badge;
      var tsEl = document.getElementById('sd-ts-line-' + i);
      if (tsEl) { tsEl.textContent = sdFmtTs(result.iso); tsEl.dataset.badge = result.badge; }
    }
  }

  function sdToggle(i) {
    sdFiles[i].selected = !sdFiles[i].selected;
    var wrap = document.querySelector('.sd-thumb-wrap[data-idx="' + i + '"]');
    if (wrap) wrap.className = 'sd-thumb-wrap' + (sdFiles[i].selected ? ' selected' : '');
    sdUpdateCount();
  }

  function sdUpdateCount() {
    var n = sdFiles.filter(function(f) { return f.selected; }).length;
    document.getElementById('sd-selected-count').textContent = n + ' selected';
    var row = document.getElementById('sd-upload-row');
    var btn = document.getElementById('sd-upload-btn');
    if (n > 0) {
      row.style.display = 'flex';
      btn.textContent = 'Import ' + n + ' selected';
    } else {
      row.style.display = 'none';
    }
  }

  function sdUpdateLoadMore() {
    var row       = document.getElementById('sd-load-more-row');
    var remaining = sdFiles.length - sdShown;
    if (remaining > 0) {
      row.style.display = 'flex';
      document.getElementById('sd-load-more-label').textContent = remaining + ' more';
    } else {
      row.style.display = 'none';
    }
  }

  function sdLoadMore() { sdAppendThumbs(SD_PAGE); }

  function sdSelectAllVisible() {
    for (var i = 0; i < sdShown; i++) {
      sdFiles[i].selected = true;
      var wrap = document.querySelector('.sd-thumb-wrap[data-idx="' + i + '"]');
      if (wrap) wrap.className = 'sd-thumb-wrap selected';
    }
    sdUpdateCount();
  }

  function sdDeselectAll() {
    sdFiles.forEach(function(f, i) {
      f.selected = false;
      var wrap = document.querySelector('.sd-thumb-wrap[data-idx="' + i + '"]');
      if (wrap) wrap.className = 'sd-thumb-wrap';
    });
    sdUpdateCount();
  }

  function sdSetThumbStatus(i, thumbStatus, detail) {
    var wrap = document.querySelector('.sd-thumb-wrap[data-idx="' + i + '"]');
    if (!wrap) return;
    var existing = wrap.querySelector('.sd-status-overlay');
    if (existing) existing.remove();
    var ov = document.createElement('div');
    ov.className = 'sd-status-overlay';
    ov.dataset.state = thumbStatus;
    ov.textContent = thumbStatus === 'uploading' ? '…' : thumbStatus === 'done' ? '✓' : '✗';
    if (detail) ov.title = detail;
    wrap.appendChild(ov);
  }

  async function sdUploadSelected() {
    var btn    = document.getElementById('sd-upload-btn');
    var status = document.getElementById('sd-upload-status');
    var queue  = sdFiles.map(function(e, i) { return {entry: e, idx: i}; })
                        .filter(function(x) { return x.entry.selected; });
    if (queue.length === 0) return;

    btn.disabled = true;
    var done = 0, failed = 0;

    for (var q = 0; q < queue.length; q++) {
      var idx   = queue[q].idx;
      var entry = queue[q].entry;
      status.textContent = (q + 1) + ' / ' + queue.length + '…';
      sdSetThumbStatus(idx, 'uploading');

      // For RAW files, wait for extraction if not done yet
      if (entry.isRaw && !entry.uploadFile) {
        try {
          var jpegBytes = await extractEmbeddedJpeg(entry.file);
          if (jpegBytes) {
            var blob = new Blob([jpegBytes], {type: 'image/jpeg'});
            entry.uploadFile = new File([blob], entry.file.name, {type: 'image/jpeg'});
            if (!entry.thumbUrl) {
              entry.thumbUrl = URL.createObjectURL(blob);
              var wrap = document.querySelector('.sd-thumb-wrap[data-idx="' + idx + '"]');
              if (wrap) {
                var img = wrap.querySelector('img');
                if (img) { img.src = entry.thumbUrl; img.style.display = ''; }
                var lbl = document.getElementById('sd-orf-lbl-' + idx);
                if (lbl) lbl.remove();
              }
            }
          }
        } catch(e) { console.warn('RAW extract failed for upload', entry.file.name, e); }
      }

      if (!entry.uploadFile) { sdSetThumbStatus(idx, 'error'); failed++; continue; }

      var ts = entry.capturedAt || new Date(entry.file.lastModified).toISOString();

      var fd = new FormData();
      fd.append('image', entry.uploadFile, entry.file.name);
      fd.append('captured_at', ts);
      var ptype = document.getElementById('sd-photo-type').value;
      if (ptype) fd.append('photo_type', ptype);

      try {
        var resp = await fetch('/manual-photos', {method: 'POST', body: fd});
        if (resp.ok) { sdSetThumbStatus(idx, 'done'); done++; }
        else         { sdSetThumbStatus(idx, 'error', 'HTTP ' + resp.status); failed++; console.warn('Upload failed', entry.file.name, resp.status); }
      } catch(e)   { sdSetThumbStatus(idx, 'error', String(e)); failed++; console.warn('Upload error', entry.file.name, e); }
    }

    btn.disabled = false;
    status.textContent = done + ' uploaded' + (failed > 0 ? ', ' + failed + ' failed' : '');
    if (done > 0) loadPhotos();
  }

  updateFlickerFps();
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
