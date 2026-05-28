import { vi, describe, it, expect, beforeAll, beforeEach } from 'vitest';

vi.mock('@/api.js', () => ({
  createEvent: vi.fn().mockResolvedValue({id: 1}),
  getEvents: vi.fn().mockResolvedValue([]),
  createLocation: vi.fn().mockResolvedValue({id: 1, name: 'Balcony'}),
  createGrowingUnit: vi.fn().mockResolvedValue({id: 1, name: 'Basil'}),
}));

let toggleManagePanel, toggleEventsPanel, createLocation, createUnit, logEvent;

beforeAll(async () => {
  document.body.innerHTML = `
    <div id="manage-form">
      <label id="manage-toggle-label">▸ expand</label>
      <input id="new-loc-name" value="">
      <input id="new-loc-desc" value="">
      <span id="loc-status"></span>
      <input id="new-unit-name" value="">
      <select id="new-unit-type"><option value="">—</option></select>
      <span id="unit-status"></span>
    </div>
    <div id="events-form">
      <label id="events-toggle-label">▸ expand</label>
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

  ({toggleManagePanel, toggleEventsPanel, createLocation, createUnit, logEvent} =
    await import('@/events.js'));
});

beforeEach(async () => {
  vi.clearAllMocks();
  const api = await import('@/api.js');
  vi.mocked(api.createEvent).mockResolvedValue({id: 1});
  vi.mocked(api.getEvents).mockResolvedValue([]);
  vi.mocked(api.createLocation).mockResolvedValue({id: 1, name: 'Balcony'});
  vi.mocked(api.createGrowingUnit).mockResolvedValue({id: 1});
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

// ── toggleManagePanel ─────────────────────────────────────

describe('toggleManagePanel', () => {
  it('toggles open class on manage-form', () => {
    document.getElementById('manage-form').classList.remove('open');
    toggleManagePanel();
    expect(document.getElementById('manage-form').classList.contains('open')).toBe(true);
    toggleManagePanel();
    expect(document.getElementById('manage-form').classList.contains('open')).toBe(false);
  });

  it('updates label text', () => {
    document.getElementById('manage-form').classList.remove('open');
    toggleManagePanel();
    expect(document.getElementById('manage-toggle-label').textContent).toBe('▾ collapse');
    toggleManagePanel();
    expect(document.getElementById('manage-toggle-label').textContent).toBe('▸ expand');
  });
});

// ── toggleEventsPanel ─────────────────────────────────────

describe('toggleEventsPanel', () => {
  it('toggles open class on events-form', () => {
    document.getElementById('events-form').classList.remove('open');
    toggleEventsPanel();
    expect(document.getElementById('events-form').classList.contains('open')).toBe(true);
  });

  it('calls getEvents when opening', async () => {
    const {getEvents} = await import('@/api.js');
    document.getElementById('events-form').classList.remove('open');
    toggleEventsPanel();
    await vi.waitFor(() => expect(getEvents).toHaveBeenCalled());
  });

  it('does not call getEvents when closing', async () => {
    const {getEvents} = await import('@/api.js');
    document.getElementById('events-form').classList.add('open');
    toggleEventsPanel();
    expect(getEvents).not.toHaveBeenCalled();
  });

  it('updates label text', () => {
    document.getElementById('events-form').classList.remove('open');
    toggleEventsPanel();
    expect(document.getElementById('events-toggle-label').textContent).toBe('▾ collapse');
  });
});

// ── createLocation ────────────────────────────────────────

describe('createLocation', () => {
  it('shows "Name required." and does not call api when name is empty', async () => {
    const {createLocation: apiCreate} = await import('@/api.js');
    document.getElementById('new-loc-name').value = '';
    await createLocation();
    expect(document.getElementById('loc-status').textContent).toBe('Name required.');
    expect(apiCreate).not.toHaveBeenCalled();
  });

  it('calls apiCreateLocation with name and description', async () => {
    const {createLocation: apiCreate} = await import('@/api.js');
    document.getElementById('new-loc-name').value = 'Balcony';
    document.getElementById('new-loc-desc').value = 'South-facing';
    await createLocation();
    expect(apiCreate).toHaveBeenCalledWith({name: 'Balcony', description: 'South-facing'});
  });

  it('passes null description when description field is empty', async () => {
    const {createLocation: apiCreate} = await import('@/api.js');
    document.getElementById('new-loc-name').value = 'Windowsill';
    document.getElementById('new-loc-desc').value = '';
    await createLocation();
    expect(apiCreate).toHaveBeenCalledWith({name: 'Windowsill', description: null});
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
    const {createLocation: apiCreate} = await import('@/api.js');
    apiCreate.mockRejectedValueOnce(new Error('duplicate name'));
    document.getElementById('new-loc-name').value = 'Balcony';
    await createLocation();
    expect(document.getElementById('loc-status').textContent).toContain('duplicate name');
  });
});

// ── createUnit ────────────────────────────────────────────

describe('createUnit', () => {
  it('shows "Name required." when name is empty', async () => {
    const {createGrowingUnit} = await import('@/api.js');
    document.getElementById('new-unit-name').value = '';
    await createUnit();
    expect(document.getElementById('unit-status').textContent).toBe('Name required.');
    expect(createGrowingUnit).not.toHaveBeenCalled();
  });

  it('calls createGrowingUnit with name and unit_type', async () => {
    const {createGrowingUnit} = await import('@/api.js');
    document.getElementById('new-unit-name').value = 'Thai basil';
    document.getElementById('new-unit-type').value = '';
    await createUnit();
    expect(createGrowingUnit).toHaveBeenCalledWith({name: 'Thai basil', unit_type: null});
  });

  it('clears the name input on success', async () => {
    document.getElementById('new-unit-name').value = 'Mint pot';
    await createUnit();
    expect(document.getElementById('new-unit-name').value).toBe('');
  });
});

// ── logEvent ──────────────────────────────────────────────

describe('logEvent', () => {
  it('calls createEvent with the selected event_type', async () => {
    const {createEvent} = await import('@/api.js');
    document.getElementById('new-event-type').value = 'watered';
    await logEvent();
    expect(createEvent).toHaveBeenCalledWith(expect.objectContaining({event_type: 'watered'}));
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

  it('shows error text when createEvent rejects', async () => {
    const {createEvent} = await import('@/api.js');
    createEvent.mockRejectedValueOnce(new Error('server error'));
    await logEvent();
    expect(document.getElementById('event-status').textContent).toContain('server error');
  });

  it('calls getEvents after a successful log', async () => {
    const {getEvents} = await import('@/api.js');
    await logEvent();
    await vi.waitFor(() => expect(getEvents).toHaveBeenCalled());
  });
});
