import { vi, describe, it, expect, beforeAll, beforeEach, afterEach } from 'vitest';
import { makeFetchMock } from './fetchHelper.js';

let createLocation, createUnit, logEvent, loadEvents;
let fetchMock;

beforeAll(async () => {
  document.body.innerHTML = `
    <div id="manage-form">
      <input id="new-loc-name" value="">
      <input id="new-loc-desc" value="">
      <span id="loc-status"></span>
      <input id="new-unit-name" value="">
      <select id="new-unit-type"><option value="">—</option></select>
      <span id="unit-status"></span>
    </div>
    <div id="events-form">
      <select id="new-event-type">
        <option value="fed_liquid">Fed liquid</option>
        <option value="watered">Watered</option>
        <option value="potted_up">Potted up</option>
      </select>
      <input id="new-event-at" value="">
      <select id="new-event-location"><option value="">—</option></select>
      <select id="new-event-units" multiple></select>
      <input id="new-event-note" value="">
      <span id="event-status"></span>
      <div id="event-list"></div>
    </div>
  `;

  ({createLocation, createUnit, logEvent, loadEvents} =
    await import('@/events.js'));
});

beforeEach(() => {
  fetchMock = makeFetchMock([
    {method: 'POST', url: '/events',        body: {id: 1}},
    {method: 'GET',  url: '/events',        body: []},
    {method: 'POST', url: '/locations',     body: {id: 1, name: 'Balcony'}},
    {method: 'POST', url: '/growing-units', body: {id: 1, name: 'Basil'}},
  ]);
  vi.stubGlobal('fetch', fetchMock);
  document.getElementById('new-loc-name').value = '';
  document.getElementById('new-loc-desc').value = '';
  document.getElementById('loc-status').textContent = '';
  document.getElementById('new-unit-name').value = '';
  document.getElementById('unit-status').textContent = '';
  document.getElementById('new-event-at').value = '';
  document.getElementById('new-event-location').value = '';
  document.getElementById('new-event-note').value = '';
  document.getElementById('event-status').textContent = '';
  document.getElementById('new-event-type').selectedIndex = 0;
});

afterEach(() => vi.unstubAllGlobals());

// ── createLocation ────────────────────────────────────────

describe('createLocation', () => {
  it('shows "Name required." and does not call api when name is empty', async () => {
    document.getElementById('new-loc-name').value = '';
    await createLocation();
    expect(document.getElementById('loc-status').textContent).toBe('Name required.');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('POSTs /locations with name and description', async () => {
    document.getElementById('new-loc-name').value = 'Balcony';
    document.getElementById('new-loc-desc').value = 'South-facing';
    await createLocation();
    expect(fetchMock).toHaveBeenCalledWith('/locations', expect.objectContaining({method: 'POST'}));
    const call = fetchMock.mock.calls.find(([u, o]) => u === '/locations' && o?.method === 'POST');
    expect(JSON.parse(call[1].body)).toEqual({name: 'Balcony', description: 'South-facing'});
  });

  it('passes null description when description field is empty', async () => {
    document.getElementById('new-loc-name').value = 'Windowsill';
    document.getElementById('new-loc-desc').value = '';
    await createLocation();
    const call = fetchMock.mock.calls.find(([u, o]) => u === '/locations' && o?.method === 'POST');
    expect(JSON.parse(call[1].body)).toEqual({name: 'Windowsill', description: null});
  });

  it('clears input fields on success', async () => {
    document.getElementById('new-loc-name').value = 'Balcony';
    document.getElementById('new-loc-desc').value = 'South-facing';
    await createLocation();
    expect(document.getElementById('new-loc-name').value).toBe('');
    expect(document.getElementById('new-loc-desc').value).toBe('');
  });

  it('shows "Added." on success', async () => {
    document.getElementById('new-loc-name').value = 'Balcony';
    await createLocation();
    expect(document.getElementById('loc-status').textContent).toBe('Added.');
  });

  it('shows error message on api failure', async () => {
    fetchMock.mockResolvedValueOnce({ok: false, status: 422, json: () => Promise.resolve({detail: 'duplicate name'})});
    document.getElementById('new-loc-name').value = 'Balcony';
    await createLocation();
    expect(document.getElementById('loc-status').textContent).toContain('duplicate name');
  });
});

// ── createUnit ────────────────────────────────────────────

describe('createUnit', () => {
  it('shows "Name required." when name is empty', async () => {
    document.getElementById('new-unit-name').value = '';
    await createUnit();
    expect(document.getElementById('unit-status').textContent).toBe('Name required.');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('POSTs /growing-units with name and unit_type', async () => {
    document.getElementById('new-unit-name').value = 'Thai basil';
    document.getElementById('new-unit-type').value = '';
    await createUnit();
    const call = fetchMock.mock.calls.find(([u, o]) => u === '/growing-units' && o?.method === 'POST');
    expect(call).toBeDefined();
    expect(JSON.parse(call[1].body)).toEqual({name: 'Thai basil', unit_type: null});
  });

  it('clears the name input on success', async () => {
    document.getElementById('new-unit-name').value = 'Mint pot';
    await createUnit();
    expect(document.getElementById('new-unit-name').value).toBe('');
  });
});

// ── loadEvents ────────────────────────────────────────────

describe('loadEvents', () => {
  beforeEach(() => {
    document.getElementById('event-list').innerHTML = '';
  });

  it('shows "No events yet." when list is empty', async () => {
    await loadEvents();
    await vi.waitFor(() => {
      expect(document.getElementById('event-list').textContent).toBe('No events yet.');
    });
  });

  it('renders event_type with underscores replaced by spaces', async () => {
    fetchMock.mockResolvedValueOnce({ok: true, status: 200, json: () => Promise.resolve([
      {id: 1, event_type: 'fed_liquid', event_at: '2026-05-01T10:00:00Z',
       location_name: null, growing_units: [], note_text: null},
    ])});
    await loadEvents();
    await vi.waitFor(() => {
      const type = document.getElementById('event-list').querySelector('.event-type');
      expect(type).not.toBeNull();
      expect(type.textContent).toBe('fed liquid');
    });
  });

  it('appends location_name to meta when present', async () => {
    fetchMock.mockResolvedValueOnce({ok: true, status: 200, json: () => Promise.resolve([
      {id: 1, event_type: 'watered', event_at: '2026-05-01T10:00:00Z',
       location_name: 'Balcony', growing_units: [], note_text: null},
    ])});
    await loadEvents();
    await vi.waitFor(() => {
      const meta = document.getElementById('event-list').querySelector('.event-meta');
      expect(meta.textContent).toContain('@ Balcony');
    });
  });

  it('omits location suffix from meta when location_name is null', async () => {
    fetchMock.mockResolvedValueOnce({ok: true, status: 200, json: () => Promise.resolve([
      {id: 1, event_type: 'watered', event_at: '2026-05-01T10:00:00Z',
       location_name: null, growing_units: [], note_text: null},
    ])});
    await loadEvents();
    await vi.waitFor(() => {
      const meta = document.getElementById('event-list').querySelector('.event-meta');
      expect(meta.textContent).not.toContain('@');
    });
  });

  it('renders growing unit names when present', async () => {
    fetchMock.mockResolvedValueOnce({ok: true, status: 200, json: () => Promise.resolve([
      {id: 1, event_type: 'watered', event_at: '2026-05-01T10:00:00Z',
       location_name: null,
       growing_units: [{id: 1, name: 'Basil'}, {id: 2, name: 'Mint'}],
       note_text: null},
    ])});
    await loadEvents();
    await vi.waitFor(() => {
      const units = document.getElementById('event-list').querySelector('.event-units');
      expect(units).not.toBeNull();
      expect(units.textContent).toBe('Basil, Mint');
    });
  });

  it('omits units div when growing_units is empty', async () => {
    fetchMock.mockResolvedValueOnce({ok: true, status: 200, json: () => Promise.resolve([
      {id: 1, event_type: 'watered', event_at: '2026-05-01T10:00:00Z',
       location_name: null, growing_units: [], note_text: null},
    ])});
    await loadEvents();
    await vi.waitFor(() => {
      expect(document.getElementById('event-list').querySelector('.event-units')).toBeNull();
    });
  });

  it('renders note_text when present', async () => {
    fetchMock.mockResolvedValueOnce({ok: true, status: 200, json: () => Promise.resolve([
      {id: 1, event_type: 'watered', event_at: '2026-05-01T10:00:00Z',
       location_name: null, growing_units: [], note_text: 'deep soak'},
    ])});
    await loadEvents();
    await vi.waitFor(() => {
      const note = document.getElementById('event-list').querySelector('.event-note');
      expect(note).not.toBeNull();
      expect(note.textContent).toBe('deep soak');
    });
  });

  it('omits note div when note_text is null', async () => {
    fetchMock.mockResolvedValueOnce({ok: true, status: 200, json: () => Promise.resolve([
      {id: 1, event_type: 'watered', event_at: '2026-05-01T10:00:00Z',
       location_name: null, growing_units: [], note_text: null},
    ])});
    await loadEvents();
    await vi.waitFor(() => {
      expect(document.getElementById('event-list').querySelector('.event-note')).toBeNull();
    });
  });
});

// ── logEvent ──────────────────────────────────────────────

describe('logEvent', () => {
  it('POSTs /events with the selected event_type', async () => {
    document.getElementById('new-event-type').value = 'watered';
    await logEvent();
    const call = fetchMock.mock.calls.find(([u, o]) => u === '/events' && o?.method === 'POST');
    expect(call).toBeDefined();
    expect(JSON.parse(call[1].body)).toMatchObject({event_type: 'watered'});
  });

  it('resets new-event-type to first option after success (Bug C fix)', async () => {
    document.getElementById('new-event-type').value = 'potted_up';
    await logEvent();
    expect(document.getElementById('new-event-type').selectedIndex).toBe(0);
  });

  it('clears new-event-at after success', async () => {
    document.getElementById('new-event-at').value = '2026-05-28T10:00';
    await logEvent();
    expect(document.getElementById('new-event-at').value).toBe('');
  });

  it('clears new-event-note after success', async () => {
    document.getElementById('new-event-note').value = 'big watering';
    await logEvent();
    expect(document.getElementById('new-event-note').value).toBe('');
  });

  it('shows "Logged." on success', async () => {
    await logEvent();
    expect(document.getElementById('event-status').textContent).toBe('Logged.');
  });

  it('shows error text when POST /events fails', async () => {
    fetchMock.mockResolvedValueOnce({ok: false, status: 500, json: () => Promise.resolve({detail: 'server error'})});
    await logEvent();
    expect(document.getElementById('event-status').textContent).toContain('server error');
  });

  it('calls GET /events after a successful log', async () => {
    await logEvent();
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/events', undefined);
    });
  });
});
