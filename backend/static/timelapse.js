import { state } from './state.js';
import { formatDate } from './utils.js';

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
  if (hasPhotos) tlShowFrame();
}

function tlShowFrame() {
  const p = state.allPhotos[state.tlIndex];
  const img = document.getElementById('tl-img');
  img.src = p.url;
  img.style.transform = p.rotation ? `rotate(${p.rotation}deg)` : '';
  document.getElementById('tl-label').textContent = formatDate(p.captured_at);
  document.getElementById('tl-counter').textContent = (state.tlIndex + 1) + ' / ' + state.allPhotos.length;
}

export function tlPlayPause() {
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

export function tlPrev() {
  tlStop();
  state.tlIndex = (state.tlIndex - 1 + state.allPhotos.length) % state.allPhotos.length;
  tlShowFrame();
}

export function tlNext() {
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
