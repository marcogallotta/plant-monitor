export function setStatus(msg) {
  document.getElementById('status').textContent = msg;
}

export function formatDate(iso) {
  return new Date(iso).toLocaleString();
}

export function rotTransform(deg) {
  if (!deg) return '';
  return 'rotate(' + deg + 'deg)' + (deg === 90 || deg === 270 ? ' scale(1.778)' : '');
}

// URL for the rotation-baked variant served by the backend, used wherever the image
// can leave the dashboard's CSS rotation (e.g. dragging a thumbnail into a browser tab).
// The `v` param busts the browser cache when a photo's rotation changes.
export function orientedUrl(photo) {
  const sep = photo.url.indexOf('?') === -1 ? '?' : '&';
  return photo.url + sep + 'oriented=1&v=' + (photo.rotation || 0);
}

export function thumbnailUrl(photo) {
  return photo.url + '/thumbnail?size=400&oriented=1&v=' + (photo.rotation || 0);
}

export function mediumUrl(photo) {
  return photo.url + '/thumbnail?size=800&v=' + (photo.rotation || 0);
}

export function populateSelect(id, items, blankLabel) {
  const sel = document.getElementById(id);
  if (!sel.multiple) {
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
