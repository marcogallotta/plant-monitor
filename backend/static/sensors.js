import { getMeterLatest, getSensorPhotoContext } from './api.js';
import { state } from './state.js';

function fmt(val, decimals) {
  return (val != null && isFinite(val)) ? Number(val).toFixed(decimals) : '?';
}

export async function loadSensorStrip() {
  const strip = document.getElementById('sensor-strip');
  if (!strip) return;
  try {
    const sensors = await getMeterLatest();
    if (!sensors.length) { strip.innerHTML = ''; return; }
    strip.innerHTML = '';
    sensors.forEach(function(s) {
      const item = document.createElement('span');
      item.className = 'sensor-item' + (s.stale ? ' sensor-stale' : '');
      item.textContent = s.name + ': ' + fmt(s.temperature_c, 1) + '°C ' + fmt(s.humidity_pct, 0) + '%';
      if (s.stale) item.title = 'Stale reading';
      strip.appendChild(item);
    });
  } catch (err) {
    console.warn('loadSensorStrip failed', err);
    strip.innerHTML = '';
  }
}

export async function loadPhotoSensorContext(photoId) {
  const container = document.getElementById('modal-sensor-context');
  if (!container) return;
  container.innerHTML = '';
  try {
    const data = await getSensorPhotoContext(photoId);
    if (state.currentPhotoId !== photoId) return;  // photo changed while request was in flight
    if (!data.available) return;
    const sensors = data.sensors.filter(function(s) { return s.readings && s.readings.length; });
    if (!sensors.length) return;
    const header = document.createElement('div');
    header.className = 'sensor-context-header';
    header.textContent = 'Sensor readings near this photo';
    container.appendChild(header);
    sensors.forEach(function(s) {
      const block = document.createElement('div');
      block.className = 'sensor-context-block';
      const name = document.createElement('span');
      name.className = 'sensor-context-name';
      name.textContent = s.name;
      block.appendChild(name);
      var readings = s.readings.slice().reverse();
      readings.forEach(function(r) {
        const row = document.createElement('div');
        row.className = 'sensor-context-row';
        const ts = new Date((r.timestamp || '').replace('Z', '+00:00'));
        const timeStr = isNaN(ts) ? '?' : ts.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
        row.textContent = timeStr + ': ' + fmt(r.temperature_c, 1) + '°C ' + fmt(r.humidity_pct, 0) + '%';
        block.appendChild(row);
      });
      container.appendChild(block);
    });
  } catch (err) {
    console.warn('loadPhotoSensorContext failed', err);
    container.innerHTML = '';
  }
}
