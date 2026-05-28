import { state } from './state.js';
import { uploadPhoto, scanCameraImport, importCameraPhotos, getThumbnailBatch } from './api.js';
import {
  isImportablePhoto, isRawPhoto, sortCameraFiles, detectSessionBoundary,
  detectAllBoundaries, scanForJpeg, deriveTimestamp, buildUploadFormData,
} from './sdImportCore.js';

const SD_PAGE = 20;
const SD_TZ   = 'Europe/Rome';

let sdFiles = [];
let sdShown = 0;
let sdMode  = 'browser'; // 'browser' | 'backend'
let _loadPhotos = null;

// Session batch state — [{start, end}], newest first
let sdBatches = [];
let sdSelectedBatchCount = 0; // leading batches that are selected
let sdRevealedBatchCount = 0; // leading batches that are rendered

function _buildBatches(n, boundaries) {
  var starts = [0].concat(boundaries).concat([n]);
  return starts.slice(0, -1).map(function(s, i) { return {start: s, end: starts[i + 1]}; });
}

function _timestamps(files) {
  return files.map(function(e) { return e.mtimeMs || (e.file && e.file.lastModified) || 0; });
}

function _initBatches() {
  var boundaries = detectAllBoundaries(_timestamps(sdFiles));
  sdBatches = _buildBatches(sdFiles.length, boundaries);
  sdSelectedBatchCount = 0;
  sdRevealedBatchCount = sdBatches.length > 0 ? 1 : 0;
}

function _autoSelectFirstBatch() {
  if (sdBatches.length === 0) return;
  var b = sdBatches[0];
  for (var i = b.start; i < b.end; i++) sdFiles[i].selected = true;
  sdSelectedBatchCount = 1;
}

function _revealBatch(idx) {
  if (idx >= sdBatches.length) return;
  var b = sdBatches[idx];
  // Mark separator at start of this batch
  sdFiles[b.start].sessionBreak = true;
  sdRevealedBatchCount = idx + 1;
  // Render only the first page; load more handles the rest
  sdAppendThumbs(Math.min(SD_PAGE, b.end - sdShown));
  _updateBatchControls();
}

function _updateBatchControls() {
  var hasOlder = sdRevealedBatchCount > sdSelectedBatchCount;
  var hasMore  = sdRevealedBatchCount < sdBatches.length;
  var addGroupBtn = document.getElementById('sd-add-group-btn');
  var addMoreBtn  = document.getElementById('sd-add-more-btn');
  if (addGroupBtn) addGroupBtn.style.display = hasOlder ? '' : 'none';
  if (addMoreBtn)  addMoreBtn.style.display  = hasMore  ? '' : 'none';
}

export function initSdImport(loadPhotos) {
  _loadPhotos = loadPhotos;
}

export function toggleSdPanel() {
  var form  = document.getElementById('sd-form');
  var label = document.getElementById('sd-toggle-label');
  var open  = form.classList.toggle('open');
  label.textContent = open ? '▾ collapse' : '▸ expand';
}

export async function handleSdScan() {
  var status = document.getElementById('sd-folder-status');
  var btn    = document.getElementById('sd-scan-btn');
  status.textContent = 'Scanning…';
  if (btn) btn.disabled = true;

  sdFiles.forEach(function(e) { if (e.thumbUrl && e.mode === 'browser') URL.revokeObjectURL(e.thumbUrl); });
  sdFiles = [];
  sdShown = 0;
  sdMode  = 'backend';
  document.getElementById('sd-grid-controls').style.display = 'none';
  document.getElementById('sd-load-more-row').style.display = 'none';
  document.getElementById('sd-grid').innerHTML = '';

  var data;
  try {
    data = await scanCameraImport();
  } catch(e) {
    status.textContent = 'Scan failed: ' + e.message;
    if (btn) btn.disabled = false;
    return;
  }

  if (btn) btn.disabled = false;

  var candidates = data.candidates || [];

  if (candidates.length === 0) {
    var msg = 'No camera/card photos found.';
    if (data.already_imported_count > 0) msg = 'All ' + data.already_imported_count + ' already imported.';
    status.textContent = msg;
    return;
  }

  sdFiles = candidates.map(function(c) {
    return {
      fileId:          c.id,
      filename:        c.filename,
      selected:        false,
      isRaw:           c.is_raw,
      thumbUrl:        c.thumbnail_url,
      capturedAt:      c.captured_at,
      tsBadge:         'mtime',
      mtimeMs:         c.mtime_ms,
      alreadyImported: c.already_imported,
      sessionBreak:    false,
      mode:            'backend',
      rotation:        0,
    };
  });

  _initBatches();
  _autoSelectFirstBatch();

  var b0count = sdBatches.length > 0 ? sdBatches[0].end : sdFiles.length;
  var batchLabel = sdBatches.length > 1 ? ' — ' + b0count + ' in latest batch' : '';
  var label = data.sources && data.sources[0] ? data.sources[0].label : 'card';
  status.textContent = label + ': ' + candidates.length + ' photo' + (candidates.length === 1 ? '' : 's') + batchLabel;

  // Auto-expand so the grid is visible without a manual click
  var form = document.getElementById('sd-form');
  var toggleLabel = document.getElementById('sd-toggle-label');
  if (!form.classList.contains('open')) {
    form.classList.add('open');
    if (toggleLabel) toggleLabel.textContent = '▾ collapse';
  }

  document.getElementById('sd-grid-controls').style.display = 'flex';
  sdAppendThumbs(sdBatches.length > 1 ? b0count : SD_PAGE);
  if (sdBatches.length > 1) {
    _revealBatch(1);
  } else {
    sdRevealedBatchCount = 1;
    _updateBatchControls();
  }
}

export async function handleSdFolderInput(event) {
  var status = document.getElementById('sd-folder-status');
  status.textContent = 'Loading…';

  // Ensure state.allPhotos is current before computing already-uploaded set
  if (_loadPhotos) await _loadPhotos();

  sdFiles.forEach(function(e) { if (e.thumbUrl && e.mode === 'browser') URL.revokeObjectURL(e.thumbUrl); });
  sdFiles = [];
  sdShown = 0;
  sdMode  = 'browser';
  document.getElementById('sd-grid-controls').style.display = 'none';
  document.getElementById('sd-load-more-row').style.display = 'none';
  document.getElementById('sd-grid').innerHTML = '';

  var uploaded = new Set(state.allPhotos.map(function(p) { return p.original_filename; }).filter(Boolean));

  var all = Array.from(event.target.files);
  var photos = all.filter(function(f) { return isImportablePhoto(f.name) && !uploaded.has(f.name); });
  var skipped = all.filter(function(f) { return isImportablePhoto(f.name) && uploaded.has(f.name); }).length;

  if (photos.length === 0) {
    status.textContent = skipped > 0 ? 'All ' + skipped + ' already imported.' : 'No photos found.';
    return;
  }

  // most recently shot first — sort by filename descending (sequential camera numbering)
  photos = sortCameraFiles(photos);

  sdFiles = photos.map(function(f) {
    var isRaw  = isRawPhoto(f.name);
    return {
      file:        f,
      filename:    f.name,
      selected:    false,
      isRaw:       isRaw,
      thumbUrl:    isRaw ? null : URL.createObjectURL(f),
      uploadFile:  isRaw ? null : f,
      capturedAt:  null,
      tsBadge:     null,
      sessionBreak: false,
      mode:        'browser',
      rotation:    0,
    };
  });

  _initBatches();
  _autoSelectFirstBatch();

  var b0count = sdBatches.length > 0 ? sdBatches[0].end : sdFiles.length;
  var batchLabel = sdBatches.length > 1 ? ' — ' + b0count + ' in latest batch' : '';
  var skipLabel  = skipped > 0 ? ' (' + skipped + ' already imported)' : '';
  status.textContent = sdFiles.length + ' photo' + (sdFiles.length === 1 ? '' : 's') + batchLabel + skipLabel;
  document.getElementById('sd-grid-controls').style.display = 'flex';
  sdAppendThumbs(sdBatches.length > 1 ? b0count : SD_PAGE);
  if (sdBatches.length > 1) {
    _revealBatch(1);
  } else {
    sdRevealedBatchCount = 1;
    _updateBatchControls();
  }
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
  if (sdMode === 'backend') {
    sdBatchLoadThumbs(from, end);
  } else {
    sdExtractRawThumbs(from, end);
    sdParseExif(from, end);
  }
}

async function sdBatchLoadThumbs(from, to) {
  var fileIds = [];
  for (var i = from; i < to; i++) {
    if (sdFiles[i] && sdFiles[i].mode === 'backend') fileIds.push(sdFiles[i].fileId);
  }
  if (fileIds.length === 0) return;
  try {
    var data = await getThumbnailBatch(fileIds);
    for (var fid in data.thumbs) {
      var img = document.querySelector('img[data-fileid="' + fid + '"]');
      if (img) img.src = 'data:image/jpeg;base64,' + data.thumbs[fid];
    }
  } catch(e) { console.warn('batch thumb load failed', e); }
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
  img.alt     = entry.filename;
  img.loading = 'lazy';
  if (entry.mode === 'backend') {
    img.dataset.fileid = entry.fileId;
    // src filled in by sdBatchLoadThumbs after render
  } else if (entry.thumbUrl) {
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
  nameSpan.textContent = entry.filename;
  var tsSpan = document.createElement('div');
  tsSpan.className = 'sd-ts-line';
  tsSpan.id        = 'sd-ts-line-' + i;
  if (entry.tsBadge) tsSpan.dataset.badge = entry.tsBadge;
  tsSpan.textContent = entry.capturedAt ? sdFmtTs(entry.capturedAt) : '';
  caption.appendChild(nameSpan);
  caption.appendChild(tsSpan);

  var check = document.createElement('div');
  check.className = 'sd-thumb-check';

  var rotBtns = document.createElement('div');
  rotBtns.className = 'sd-rot-btns';
  var rotL = document.createElement('button');
  rotL.textContent = '↺';
  rotL.title = 'Rotate left';
  rotL.addEventListener('click', function(e) { e.stopPropagation(); sdRotate(i, -90); });
  var rotR = document.createElement('button');
  rotR.textContent = '↻';
  rotR.title = 'Rotate right';
  rotR.addEventListener('click', function(e) { e.stopPropagation(); sdRotate(i, 90); });
  rotBtns.appendChild(rotL);
  rotBtns.appendChild(rotR);

  wrap.appendChild(img);
  wrap.appendChild(rotBtns);
  wrap.appendChild(caption);
  wrap.appendChild(check);
  return wrap;
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
  }
  var bytes = new Uint8Array(await file.arrayBuffer());
  return scanForJpeg(bytes).jpeg;
}

async function sdExtractRawThumbs(from, to) {
  for (var i = from; i < to; i++) {
    var entry = sdFiles[i];
    if (entry.mode === 'backend' || !entry.isRaw || entry.thumbUrl) continue;
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

function sdFmtTs(iso) {
  try {
    return new Date(iso).toLocaleString('sv-SE', {timeZone: SD_TZ,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit'}).replace('T', ' ');
  } catch(e) { return iso.slice(0, 16); }
}

async function sdParseExif(from, to) {
  for (var i = from; i < to; i++) {
    var entry = sdFiles[i];
    if (entry.mode === 'backend' || entry.capturedAt) continue;
    var exif = null;
    try {
      // exifr can read JPEG and ARW; ORF is not supported — will return null
      exif = await window.exifr.parse(entry.file, ['DateTimeOriginal', 'CreateDate', 'OffsetTimeOriginal']);
    } catch(e) { /* unsupported format — fallback below */ }
    var result      = deriveTimestamp(exif, entry.file);
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

function sdRotate(i, delta) {
  sdFiles[i].rotation = ((sdFiles[i].rotation || 0) + delta + 360) % 360;
  var wrap = document.querySelector('.sd-thumb-wrap[data-idx="' + i + '"]');
  if (wrap) {
    var img = wrap.querySelector('img');
    if (img) img.style.transform = sdFiles[i].rotation ? 'rotate(' + sdFiles[i].rotation + 'deg)' : '';
  }
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

function _revealedEnd() {
  if (sdRevealedBatchCount === 0 || sdBatches.length === 0) return 0;
  return sdBatches[Math.min(sdRevealedBatchCount, sdBatches.length) - 1].end;
}

function sdUpdateLoadMore() {
  var row       = document.getElementById('sd-load-more-row');
  var remaining = _revealedEnd() - sdShown;
  if (remaining > 0) {
    row.style.display = 'flex';
    document.getElementById('sd-load-more-label').textContent = remaining + ' more';
  } else {
    row.style.display = 'none';
  }
}

export function sdLoadMore() {
  var count = Math.min(SD_PAGE, _revealedEnd() - sdShown);
  if (count > 0) sdAppendThumbs(count);
}

export function sdAddMore() {
  if (sdRevealedBatchCount >= sdBatches.length) return;
  _revealBatch(sdRevealedBatchCount);
}

export function sdAddGroup() {
  if (sdRevealedBatchCount <= sdSelectedBatchCount) return;

  // Select all revealed-but-unselected files and remove their separators from the DOM
  for (var b = sdSelectedBatchCount; b < sdRevealedBatchCount; b++) {
    var batch = sdBatches[b];
    for (var i = batch.start; i < batch.end; i++) {
      sdFiles[i].selected = true;
      var wrap = document.querySelector('.sd-thumb-wrap[data-idx="' + i + '"]');
      if (wrap) wrap.className = 'sd-thumb-wrap selected';
    }
    // Remove separator DOM node before the first thumb of this batch
    var firstWrap = document.querySelector('.sd-thumb-wrap[data-idx="' + batch.start + '"]');
    if (firstWrap) {
      var prev = firstWrap.previousElementSibling;
      if (prev && prev.classList.contains('sd-session-break')) prev.remove();
    }
    sdFiles[batch.start].sessionBreak = false;
  }
  sdSelectedBatchCount = sdRevealedBatchCount;

  sdUpdateCount();

  // Reveal next batch as the new "older" section
  if (sdRevealedBatchCount < sdBatches.length) {
    _revealBatch(sdRevealedBatchCount);
  } else {
    _updateBatchControls();
  }
}

export function sdSelectAllVisible() {
  for (var i = 0; i < sdShown; i++) {
    sdFiles[i].selected = true;
    var wrap = document.querySelector('.sd-thumb-wrap[data-idx="' + i + '"]');
    if (wrap) wrap.className = 'sd-thumb-wrap selected';
  }
  sdUpdateCount();
}

export function sdDeselectAll() {
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

export async function sdUploadSelected() {
  var btn    = document.getElementById('sd-upload-btn');
  var status = document.getElementById('sd-upload-status');
  var queue  = sdFiles.map(function(e, i) { return {entry: e, idx: i}; })
                      .filter(function(x) { return x.entry.selected; });
  if (queue.length === 0) return;

  btn.disabled = true;

  if (sdMode === 'backend') {
    await sdUploadBackend(queue, btn, status);
  } else {
    await sdUploadBrowser(queue, btn, status);
  }
}

async function sdUploadBackend(queue, btn, status) {
  var ptype     = document.getElementById('sd-photo-type').value;
  var fileIds   = queue.map(function(q) { return q.entry.fileId; });
  var rotations = {};
  queue.forEach(function(q) { if (q.entry.rotation != null) rotations[q.entry.fileId] = q.entry.rotation; });

  queue.forEach(function(q) { sdSetThumbStatus(q.idx, 'uploading'); });
  status.textContent = 'Importing…';

  var result;
  try {
    result = await importCameraPhotos({file_ids: fileIds, photo_type: ptype || null, rotations: rotations});
  } catch(e) {
    status.textContent = 'Import failed: ' + e.message;
    queue.forEach(function(q) { sdSetThumbStatus(q.idx, 'error', e.message); });
    btn.disabled = false;
    return;
  }

  var idxByFileId = {};
  queue.forEach(function(q) { idxByFileId[q.entry.fileId] = q.idx; });

  (result.created || []).forEach(function(r) {
    var idx = idxByFileId[r.file_id];
    if (idx !== undefined) sdSetThumbStatus(idx, 'done');
  });
  (result.skipped || []).forEach(function(r) {
    var idx = idxByFileId[r.file_id];
    if (idx !== undefined) sdSetThumbStatus(idx, 'done', 'already imported');
  });
  (result.failed || []).forEach(function(r) {
    var idx = idxByFileId[r.file_id];
    if (idx !== undefined) sdSetThumbStatus(idx, 'error', r.reason);
  });

  var nc = (result.created || []).length;
  var ns = (result.skipped || []).length;
  var nf = (result.failed  || []).length;
  var parts = [];
  if (nc > 0) parts.push(nc + ' imported');
  if (ns > 0) parts.push(ns + ' skipped');
  if (nf > 0) parts.push(nf + ' failed');
  status.textContent = parts.join(', ') || 'Nothing imported';

  btn.disabled = false;
  if (nc > 0 && _loadPhotos) _loadPhotos();
}

async function sdUploadBrowser(queue, btn, status) {
  var done = 0, failed = 0;

  for (var q = 0; q < queue.length; q++) {
    var idx   = queue[q].idx;
    var entry = queue[q].entry;
    status.textContent = (q + 1) + ' / ' + queue.length + '…';
    sdSetThumbStatus(idx, 'uploading');

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

    var ts    = entry.capturedAt || new Date(entry.file.lastModified).toISOString();
    var ptype = document.getElementById('sd-photo-type').value;
    var fd    = buildUploadFormData(entry.uploadFile, entry.file.name, ts, ptype, entry.rotation || 0, entry.file.size);

    try {
      await uploadPhoto(fd);
      sdSetThumbStatus(idx, 'done'); done++;
    } catch(e) { sdSetThumbStatus(idx, 'error', String(e)); failed++; console.warn('Upload error', entry.file.name, e); }
  }

  btn.disabled = false;
  status.textContent = done + ' uploaded' + (failed > 0 ? ', ' + failed + ' failed' : '');
  if (done > 0 && _loadPhotos) _loadPhotos();
}
