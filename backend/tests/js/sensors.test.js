import { vi, describe, it, expect, beforeAll, beforeEach, afterEach } from 'vitest';
import { makeFetchMock } from './fetchHelper.js';

let loadSensorStrip, loadPhotoSensorContext;
let state;

beforeAll(async () => {
  document.body.innerHTML = `
    <div id="sensor-strip"></div>
    <div id="modal-sensor-context"></div>
  `;
  ({loadSensorStrip, loadPhotoSensorContext} = await import('@/sensors.js'));
  ({state} = await import('@/state.js'));
});

beforeEach(() => {
  document.getElementById('sensor-strip').innerHTML = '';
  document.getElementById('modal-sensor-context').innerHTML = '';
});

afterEach(() => vi.unstubAllGlobals());

// ── loadSensorStrip ───────────────────────────────────────

describe('loadSensorStrip', () => {
  it('clears strip when sensors not available', async () => {
    vi.stubGlobal('fetch', makeFetchMock([
      {url: '/sensors/latest', body: {available: false, sensors: []}},
    ]));
    document.getElementById('sensor-strip').innerHTML = '<span>old</span>';
    await loadSensorStrip();
    expect(document.getElementById('sensor-strip').innerHTML).toBe('');
  });

  it('renders one item per sensor', async () => {
    vi.stubGlobal('fetch', makeFetchMock([{url: '/sensors/latest', body: {
      available: true,
      sensors: [
        {name: 'South', temperature_c: 22.5, humidity_pct: 55, stale: false},
        {name: 'North', temperature_c: 19.0, humidity_pct: 60, stale: false},
      ],
    }}]));
    await loadSensorStrip();
    expect(document.getElementById('sensor-strip').querySelectorAll('.sensor-item').length).toBe(2);
  });

  it('formats temperature to 1 decimal and humidity to 0 decimals', async () => {
    vi.stubGlobal('fetch', makeFetchMock([{url: '/sensors/latest', body: {
      available: true,
      sensors: [{name: 'South', temperature_c: 22.567, humidity_pct: 55.9, stale: false}],
    }}]));
    await loadSensorStrip();
    const item = document.getElementById('sensor-strip').querySelector('.sensor-item');
    expect(item.textContent).toBe('South: 22.6°C 56%');
  });

  it('formats null readings as "?"', async () => {
    vi.stubGlobal('fetch', makeFetchMock([{url: '/sensors/latest', body: {
      available: true,
      sensors: [{name: 'South', temperature_c: null, humidity_pct: null, stale: false}],
    }}]));
    await loadSensorStrip();
    const item = document.getElementById('sensor-strip').querySelector('.sensor-item');
    expect(item.textContent).toContain('?°C');
    expect(item.textContent).toContain('?%');
  });

  it('adds sensor-stale class and title for stale sensor', async () => {
    vi.stubGlobal('fetch', makeFetchMock([{url: '/sensors/latest', body: {
      available: true,
      sensors: [{name: 'South', temperature_c: 22.0, humidity_pct: 50, stale: true}],
    }}]));
    await loadSensorStrip();
    const item = document.getElementById('sensor-strip').querySelector('.sensor-item');
    expect(item.classList.contains('sensor-stale')).toBe(true);
    expect(item.title).toBe('Stale reading');
  });

  it('does not add sensor-stale class for fresh sensor', async () => {
    vi.stubGlobal('fetch', makeFetchMock([{url: '/sensors/latest', body: {
      available: true,
      sensors: [{name: 'South', temperature_c: 22.0, humidity_pct: 50, stale: false}],
    }}]));
    await loadSensorStrip();
    const item = document.getElementById('sensor-strip').querySelector('.sensor-item');
    expect(item.classList.contains('sensor-stale')).toBe(false);
  });

  it('clears strip on API error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')));
    document.getElementById('sensor-strip').innerHTML = '<span>old</span>';
    await loadSensorStrip();
    expect(document.getElementById('sensor-strip').innerHTML).toBe('');
  });
});

// ── loadPhotoSensorContext ────────────────────────────────

describe('loadPhotoSensorContext', () => {
  it('leaves container empty when not available', async () => {
    vi.stubGlobal('fetch', makeFetchMock([
      {url: '/sensors/photos/5', body: {available: false, sensors: []}},
    ]));
    state.currentPhotoId = 5;
    await loadPhotoSensorContext(5);
    expect(document.getElementById('modal-sensor-context').innerHTML).toBe('');
  });

  it('returns early without rendering when photo changed during request', async () => {
    vi.stubGlobal('fetch', makeFetchMock([{url: '/sensors/photos/1', body: {
      available: true,
      sensors: [{name: 'South', readings: [
        {timestamp: '2026-01-01T10:00:00Z', temperature_c: 22, humidity_pct: 55},
      ]}],
    }}]));
    state.currentPhotoId = 99;
    await loadPhotoSensorContext(1);
    expect(document.getElementById('modal-sensor-context').innerHTML).toBe('');
  });

  it('renders a header and one block per sensor that has readings', async () => {
    vi.stubGlobal('fetch', makeFetchMock([{url: '/sensors/photos/5', body: {
      available: true,
      sensors: [
        {name: 'South', readings: [{timestamp: '2026-01-01T10:00:00Z', temperature_c: 22.3, humidity_pct: 55}]},
        {name: 'North', readings: [{timestamp: '2026-01-01T10:05:00Z', temperature_c: 18.0, humidity_pct: 62}]},
      ],
    }}]));
    state.currentPhotoId = 5;
    await loadPhotoSensorContext(5);
    const container = document.getElementById('modal-sensor-context');
    expect(container.querySelector('.sensor-context-header')).not.toBeNull();
    expect(container.querySelectorAll('.sensor-context-block').length).toBe(2);
  });

  it('renders sensor name inside each block', async () => {
    vi.stubGlobal('fetch', makeFetchMock([{url: '/sensors/photos/5', body: {
      available: true,
      sensors: [
        {name: 'South', readings: [{timestamp: '2026-01-01T10:00:00Z', temperature_c: 22.3, humidity_pct: 55}]},
      ],
    }}]));
    state.currentPhotoId = 5;
    await loadPhotoSensorContext(5);
    const name = document.getElementById('modal-sensor-context').querySelector('.sensor-context-name');
    expect(name.textContent).toBe('South');
  });

  it('renders one row per reading inside each block (readings reversed)', async () => {
    vi.stubGlobal('fetch', makeFetchMock([{url: '/sensors/photos/5', body: {
      available: true,
      sensors: [{name: 'South', readings: [
        {timestamp: '2026-01-01T10:00:00Z', temperature_c: 20, humidity_pct: 50},
        {timestamp: '2026-01-01T10:05:00Z', temperature_c: 21, humidity_pct: 51},
      ]}],
    }}]));
    state.currentPhotoId = 5;
    await loadPhotoSensorContext(5);
    const rows = document.getElementById('modal-sensor-context').querySelectorAll('.sensor-context-row');
    expect(rows.length).toBe(2);
  });

  it('skips sensors with no readings', async () => {
    vi.stubGlobal('fetch', makeFetchMock([{url: '/sensors/photos/5', body: {
      available: true,
      sensors: [
        {name: 'Empty', readings: []},
        {name: 'South', readings: [{timestamp: '2026-01-01T10:00:00Z', temperature_c: 22, humidity_pct: 55}]},
      ],
    }}]));
    state.currentPhotoId = 5;
    await loadPhotoSensorContext(5);
    expect(document.getElementById('modal-sensor-context').querySelectorAll('.sensor-context-block').length).toBe(1);
  });

  it('clears container on API error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')));
    state.currentPhotoId = 5;
    document.getElementById('modal-sensor-context').innerHTML = '<div>old</div>';
    await loadPhotoSensorContext(5);
    expect(document.getElementById('modal-sensor-context').innerHTML).toBe('');
  });
});
