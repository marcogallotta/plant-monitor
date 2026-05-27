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
