import { state } from './state.js';
import { formatDate } from './utils.js';
import { parseStab, commonCrop, renderFrame } from './stabilize.js';

let tlCrop = { x0: 0, y0: 0, x1: 1, y1: 1 };

function tlStabOn() {
  const el = document.getElementById('tl-stab');
  return !!(el && el.checked);
}

// The frames currently in play. If any loaded frame carries a transform, the
// timeline is the stabilizable set (night / unalignable frames dropped) — and it
// stays that set REGARDLESS of the toggle. Flipping Stabilize only warps/unwarps;
// it must not change which frames play (that looked like it was wiping the user's
// source filter). Falls back to all frames when nothing is stabilizable.
// Computed on demand so it can never go stale against state.allPhotos.
function tlFrames() {
  const stab = state.allPhotos.filter(p => parseStab(p));
  const frames = stab.length ? stab : state.allPhotos;
  return [...frames].reverse();
}

export function tlInit() {
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

  // Only offer stabilization when some loaded frames actually carry a transform.
  const stabs = state.allPhotos.map(parseStab);
  const canStab = stabs.some(Boolean);
  const lbl = document.getElementById('tl-stab-label');
  if (lbl) lbl.style.display = canStab ? '' : 'none';
  tlCrop = canStab ? commonCrop(stabs.filter(Boolean)) : { x0: 0, y0: 0, x1: 1, y1: 1 };

  if (hasPhotos) tlShowFrame();
}

function tlShowFrame() {
  const frames = tlFrames();
  if (state.tlIndex >= frames.length) state.tlIndex = 0;
  const p = frames[state.tlIndex];
  if (!p) return;
  renderFrame(
    document.getElementById('tl-img'),
    document.getElementById('tl-canvas'),
    p, tlCrop, { stabilize: tlStabOn() },
  );
  document.getElementById('tl-label').textContent = formatDate(p.captured_at);
  document.getElementById('tl-counter').textContent = (state.tlIndex + 1) + ' / ' + frames.length;
}

export function tlPlayPause() {
  if (state.tlTimer) { tlStop(); return; }
  const btn = document.getElementById('tl-play');
  btn.textContent = '⏸ Pause';
  btn.classList.add('active');
  const fps = parseInt(document.getElementById('tl-speed').value, 10);
  state.tlTimer = setInterval(function() {
    state.tlIndex = (state.tlIndex + 1) % tlFrames().length;
    tlShowFrame();
  }, 1000 / fps);
}

function tlStop() {
  if (state.tlTimer) { clearInterval(state.tlTimer); state.tlTimer = null; }
  const btn = document.getElementById('tl-play');
  btn.textContent = '▶ Play';
  btn.classList.remove('active');
}

export function tlPrev() {
  tlStop();
  const n = tlFrames().length;
  state.tlIndex = (state.tlIndex - 1 + n) % n;
  tlShowFrame();
}

export function tlNext() {
  tlStop();
  state.tlIndex = (state.tlIndex + 1) % tlFrames().length;
  tlShowFrame();
}

function tlFps() { return parseInt(document.getElementById('tl-speed').value, 10); }

document.getElementById('tl-speed').addEventListener('input', function() {
  document.getElementById('tl-fps').textContent = tlFps() + ' fps';
  if (state.tlTimer) { tlStop(); tlPlayPause(); }
});

document.getElementById('tl-stab')?.addEventListener('change', function() {
  if (!state.allPhotos.length) return;
  tlStop();
  tlShowFrame();  // same frame set, just re-rendered warped or raw
});

document.getElementById('tl-fps').textContent = tlFps() + ' fps';
