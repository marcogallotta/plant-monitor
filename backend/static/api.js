async function apiRequest(url, options) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'HTTP ' + resp.status);
  }
  return resp.json();
}

function apiJson(url, method, body) {
  return apiRequest(url, {
    method,
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
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
  if (params.start)    p.push('start='           + encodeURIComponent(params.start));
  if (params.end)      p.push('end='             + encodeURIComponent(params.end));
  if (params.source)   p.push('source='          + encodeURIComponent(params.source));
  if (params.ptype)    p.push('photo_type='      + encodeURIComponent(params.ptype));
  if (params.location) p.push('location_id='     + encodeURIComponent(params.location));
  if (params.unit)     p.push('growing_unit_id=' + encodeURIComponent(params.unit));
  return apiRequest('/photos' + (p.length ? '?' + p.join('&') : ''));
}

export function updatePhoto(id, body)          { return apiJson('/photos/' + id, 'PUT', body); }

export function getNotes(photoId)              { return apiRequest('/photos/' + photoId + '/notes'); }
export function createNote(photoId, body)      { return apiJson('/photos/' + photoId + '/notes', 'POST', body); }
export function updateNote(noteId, body)       { return apiJson('/notes/' + noteId, 'PUT', body); }
export async function deleteNote(noteId) {
  const resp = await fetch('/notes/' + noteId, {method: 'DELETE'});
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
}

export function createLocation(body)           { return apiJson('/locations', 'POST', body); }
export function createGrowingUnit(body)        { return apiJson('/growing-units', 'POST', body); }
export function createEvent(body)              { return apiJson('/events', 'POST', body); }
export function getEvents()                    { return apiRequest('/events'); }

export function uploadPhoto(formData)          { return apiRequest('/manual-photos', {method: 'POST', body: formData}); }
