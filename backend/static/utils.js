export function setStatus(msg) {
  document.getElementById('status').textContent = msg;
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
