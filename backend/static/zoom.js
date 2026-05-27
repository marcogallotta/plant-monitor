import { state } from './state.js';
import { openCreateForm } from './notes.js';

export function applyTransform() {
  document.getElementById('modal-img-wrap').style.transform =
    'translate(' + state.panX + 'px, ' + state.panY + 'px) scale(' + state.zoom + ') rotate(' + state.currentRotation + 'deg)';
}

export function visualToStored(rx, ry) {
  var x, y;
  if (state.currentRotation === 90)       { x = ry;     y = 1 - rx; }
  else if (state.currentRotation === 180) { x = 1 - rx; y = 1 - ry; }
  else if (state.currentRotation === 270) { x = 1 - ry; y = rx;     }
  else                              { x = rx;      y = ry;     }
  return {x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y))};
}

export function resetZoom() {
  state.zoom = 1; state.panX = 0; state.panY = 0;
  state.isDrawingRect = false; state.rectStart = null;
  document.getElementById('rect-preview').style.display = 'none';
  applyTransform();
}

function clampPan() {
  const img = document.getElementById('modal-img');
  const W = img.offsetWidth, H = img.offsetHeight;
  state.panX = Math.min(0, Math.max(W  * (1 - state.zoom), state.panX));
  state.panY = Math.min(0, Math.max(H * (1 - state.zoom), state.panY));
}

function imgCoordsFromEvent(e) {
  var r = document.getElementById('modal-img').getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
    y: Math.max(0, Math.min(1, (e.clientY - r.top)  / r.height)),
  };
}

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
