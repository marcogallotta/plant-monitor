async function apiRequest(url, options) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'HTTP ' + resp.status);
  }
  return resp.json();
}

export async function getLocations() {
  const resp = await fetch('/locations');
  return resp.ok ? resp.json() : [];
}

export async function getGrowingUnits() {
  const resp = await fetch('/growing-units');
  return resp.ok ? resp.json() : [];
}

export async function getPhotos(params) {
  const p = [];
  if (params.start)    p.push('start='            + encodeURIComponent(params.start));
  if (params.end)      p.push('end='              + encodeURIComponent(params.end));
  if (params.source)   p.push('source='           + encodeURIComponent(params.source));
  if (params.ptype)    p.push('photo_type='       + encodeURIComponent(params.ptype));
  if (params.location) p.push('location_id='      + encodeURIComponent(params.location));
  if (params.unit)     p.push('growing_unit_id='  + encodeURIComponent(params.unit));
  const url = '/photos' + (p.length ? '?' + p.join('&') : '');
  const resp = await fetch(url);
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
  return resp.json();
}

export async function updatePhoto(id, body) {
  return apiRequest('/photos/' + id, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
}

export async function getNotes(photoId) {
  const resp = await fetch('/photos/' + photoId + '/notes');
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
  return resp.json();
}

export async function createNote(photoId, body) {
  return apiRequest('/photos/' + photoId + '/notes', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
}

export async function updateNote(noteId, body) {
  return apiRequest('/notes/' + noteId, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
}

export async function deleteNote(noteId) {
  const resp = await fetch('/notes/' + noteId, {method: 'DELETE'});
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
}

export async function createLocation(body) {
  return apiRequest('/locations', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
}

export async function createGrowingUnit(body) {
  return apiRequest('/growing-units', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
}

export async function createEvent(body) {
  return apiRequest('/events', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
}

export async function getEvents() {
  const resp = await fetch('/events');
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
  return resp.json();
}

export async function uploadPhoto(formData) {
  const resp = await fetch('/manual-photos', {method: 'POST', body: formData});
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'HTTP ' + resp.status);
  }
  return resp.json();
}
