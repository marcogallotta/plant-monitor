let suggestions = [];
let currentIndex = 0;
let resolving = false;

function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

export async function initReview() {
  await loadSuggestions();
}

async function loadSuggestions() {
  try {
    const resp = await fetch('/suggestions');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    suggestions = await resp.json();
    currentIndex = 0;
    render();
  } catch (e) {
    document.getElementById('review-status').textContent = 'Failed to load suggestions: ' + e.message;
  }
}

function render() {
  const counter = document.getElementById('review-counter');
  const container = document.getElementById('review-container');

  if (suggestions.length === 0) {
    counter.textContent = 'No pending suggestions';
    container.innerHTML = '<div class="review-empty">All caught up.</div>';
    return;
  }

  counter.textContent = `${currentIndex + 1} / ${suggestions.length} pending`;

  container.innerHTML = suggestions.map((s, i) => {
    const active = i === currentIndex;
    const date = s.photo_captured_at ? new Date(s.photo_captured_at).toLocaleDateString() : '';
    const conf = s.confidence ? `<span class="review-conf review-conf-${esc(s.confidence)}">${esc(s.confidence)}</span>` : '';
    const labels = (s.suggested_labels || []).map(esc).join(', ');
    const hasRegion = [s.x, s.y, s.x2, s.y2].every(v => v != null);
    const region = hasRegion ? buildRegionOverlay(s) : '';
    const actions = `
        <div class="review-actions">
          <button class="review-btn-accept" onclick="event.stopPropagation(); reviewResolve('accept', ${i})" title="Accept (A)">Accept</button>
          <button class="review-btn-reject" onclick="event.stopPropagation(); reviewResolve('reject', ${i})" title="Reject (R)">Reject</button>
          <button class="review-btn-delete" onclick="event.stopPropagation(); reviewResolve('deleted', ${i})" title="Delete photo (D)">Delete photo</button>
        </div>`;

    return `<div class="review-card${active ? ' active' : ''}" data-index="${i}" onclick="reviewFocus(${i})">
      <div class="review-photo-wrap" onclick="event.stopPropagation(); reviewOpenPhoto(${i})" style="cursor:zoom-in;">
        <img src="${esc(s.photo_url)}" alt="" loading="lazy">
        ${region}
      </div>
      <div class="review-detail">
        <div class="review-plant">${s.suggested_plant_name ? esc(s.suggested_plant_name) : '<em>unknown</em>'}</div>
        <div class="review-meta">
          ${s.suggested_photo_type ? `<span>${esc(s.suggested_photo_type)}</span>` : ''}
          ${conf}
          ${s.suggested_rotation != null ? `<span class="review-rotation">↻ ${esc(String(s.suggested_rotation))}°</span>` : ''}
          ${date ? `<span class="review-date">${esc(date)}</span>` : ''}
        </div>
        ${labels ? `<div class="review-labels">${labels}</div>` : ''}
        ${s.observation ? `<div class="review-obs">"${esc(s.observation)}"</div>` : ''}
        ${s.question ? `<div class="review-question">⚠ ${esc(s.question)}</div>` : ''}
        ${s.batch_hint ? `<div class="review-hint">Hint: ${esc(s.batch_hint)}</div>` : ''}
        ${actions}
      </div>
    </div>`;
  }).join('');

  const activeCard = container.querySelector('.review-card.active');
  if (activeCard) activeCard.scrollIntoView({ block: 'nearest' });
}

function buildRegionOverlay(s) {
  const left   = Math.min(s.x, s.x2) * 100;
  const top    = Math.min(s.y, s.y2) * 100;
  const width  = Math.abs(s.x2 - s.x) * 100;
  const height = Math.abs(s.y2 - s.y) * 100;
  return `<div class="review-region" style="left:${left}%;top:${top}%;width:${width}%;height:${height}%;"></div>`;
}

export function reviewOpenPhoto(index) {
  const s = suggestions[index];
  if (!s) return;
  window.openModalForPhoto({ id: s.photo_id, url: s.photo_url, captured_at: s.photo_captured_at, rotation: s.photo_rotation ?? 0 });
}

export function reviewFocus(index) {
  currentIndex = index;
  render();
}

export async function reviewResolve(action, index = currentIndex) {
  if (resolving || suggestions.length === 0) return;
  if (action === 'deleted' && !confirm('Delete this photo? This cannot be undone.')) return;
  resolving = true;

  const s = suggestions[index];
  const status = document.getElementById('review-status');
  status.textContent = '';

  try {
    const resp = await fetch(`/suggestions/${s.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'HTTP ' + resp.status);
    }
    suggestions.splice(index, 1);
    if (currentIndex >= suggestions.length) currentIndex = Math.max(0, suggestions.length - 1);
    render();
  } catch (e) {
    status.textContent = 'Error: ' + e.message;
  } finally {
    resolving = false;
  }
}

function isTypingTarget(el) {
  return el && (
    el.tagName === 'INPUT' ||
    el.tagName === 'TEXTAREA' ||
    el.tagName === 'SELECT' ||
    el.isContentEditable
  );
}

export function reviewKeydown(e) {
  if (!document.getElementById('tab-review')?.classList.contains('active')) return;
  if (isTypingTarget(e.target)) return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;

  const key = e.key.toLowerCase();

  if (key === 'a') { e.preventDefault(); reviewResolve('accept'); }
  if (key === 'r') { e.preventDefault(); reviewResolve('reject'); }
  if (key === 'd') { e.preventDefault(); reviewResolve('deleted'); }

  if ((key === 'arrowdown' || key === 'j') && suggestions.length) {
    e.preventDefault();
    currentIndex = Math.min(currentIndex + 1, suggestions.length - 1);
    render();
  }
  if ((key === 'arrowup' || key === 'k') && suggestions.length) {
    e.preventDefault();
    currentIndex = Math.max(currentIndex - 1, 0);
    render();
  }
}
