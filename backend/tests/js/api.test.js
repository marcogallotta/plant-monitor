import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  getLocations, getGrowingUnits, getPhotos, updatePhoto,
  getNotes, createNote, updateNote, deleteNote,
  createLocation, createGrowingUnit, createEvent, getEvents, uploadPhoto,
} from '@/api.js';

function mockFetch({ok = true, status = 200, body = {}, jsonFails = false} = {}) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: jsonFails
      ? () => Promise.reject(new Error('invalid json'))
      : () => Promise.resolve(body),
  });
}

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch({body: []}));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── success path ──────────────────────────────────────────

describe('successful requests', () => {
  it('getLocations returns parsed JSON', async () => {
    const data = [{id: 1, name: 'Balcony'}];
    vi.stubGlobal('fetch', mockFetch({body: data}));
    await expect(getLocations()).resolves.toEqual(data);
  });

  it('updatePhoto sends PUT with JSON body', async () => {
    const fetchMock = mockFetch({body: {id: 5}});
    vi.stubGlobal('fetch', fetchMock);
    await updatePhoto(5, {rotation: 90});
    expect(fetchMock.mock.calls[0][0]).toBe('/photos/5');
    expect(fetchMock.mock.calls[0][1].method).toBe('PUT');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({rotation: 90});
  });

  it('createNote sends POST to correct URL', async () => {
    const fetchMock = mockFetch({body: {id: 1}});
    vi.stubGlobal('fetch', fetchMock);
    await createNote(42, {note_text: 'hi', x: 0.5, y: 0.5});
    expect(fetchMock.mock.calls[0][0]).toBe('/photos/42/notes');
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
  });
});

// ── error handling ────────────────────────────────────────

describe('error handling', () => {
  it('throws the detail message when server returns one', async () => {
    vi.stubGlobal('fetch', mockFetch({ok: false, status: 404, body: {detail: 'Not found'}}));
    await expect(getLocations()).rejects.toThrow('Not found');
  });

  it('falls back to HTTP status when response has no detail', async () => {
    vi.stubGlobal('fetch', mockFetch({ok: false, status: 422, body: {}}));
    await expect(getLocations()).rejects.toThrow('HTTP 422');
  });

  it('falls back to HTTP status when JSON parsing fails', async () => {
    vi.stubGlobal('fetch', mockFetch({ok: false, status: 500, jsonFails: true}));
    await expect(getLocations()).rejects.toThrow('HTTP 500');
  });
});

// ── getPhotos query string ────────────────────────────────

describe('getPhotos', () => {
  it('always includes limit and offset params', async () => {
    const fetchMock = mockFetch({body: {photos: [], total: 0}});
    vi.stubGlobal('fetch', fetchMock);
    await getPhotos({});
    const url = fetchMock.mock.calls[0][0];
    expect(url).toContain('limit=60');
    expect(url).toContain('offset=0');
  });

  it('builds a query string from all provided params', async () => {
    const fetchMock = mockFetch({body: {photos: [], total: 0}});
    vi.stubGlobal('fetch', fetchMock);
    await getPhotos({source: 'pi', ptype: 'overview', location: '1', unit: '2', limit: 60, offset: 0});
    const url = fetchMock.mock.calls[0][0];
    expect(url).toContain('source=pi');
    expect(url).toContain('photo_type=overview');
    expect(url).toContain('location_id=1');
    expect(url).toContain('growing_unit_id=2');
  });

  it('omits filter params that are empty/falsy but always sends limit and offset', async () => {
    const fetchMock = mockFetch({body: {photos: [], total: 0}});
    vi.stubGlobal('fetch', fetchMock);
    await getPhotos({source: '', ptype: null, location: undefined, unit: ''});
    const url = fetchMock.mock.calls[0][0];
    expect(url).not.toContain('source=');
    expect(url).toContain('limit=');
    expect(url).toContain('offset=');
  });
});

// ── deleteNote ────────────────────────────────────────────

describe('deleteNote', () => {
  it('sends DELETE to the correct URL', async () => {
    const fetchMock = mockFetch();
    vi.stubGlobal('fetch', fetchMock);
    await deleteNote(7);
    expect(fetchMock.mock.calls[0][0]).toBe('/notes/7');
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE');
  });

  it('throws on non-ok response', async () => {
    vi.stubGlobal('fetch', mockFetch({ok: false, status: 404}));
    await expect(deleteNote(7)).rejects.toThrow('HTTP 404');
  });
});

// ── getGrowingUnits ───────────────────────────────────────

describe('getGrowingUnits', () => {
  it('fetches /growing-units and returns parsed JSON', async () => {
    const data = [{id: 1, name: 'Basil pot'}];
    vi.stubGlobal('fetch', mockFetch({body: data}));
    await expect(getGrowingUnits()).resolves.toEqual(data);
    const fetchMock = vi.fn().mockResolvedValue({ok: true, json: () => Promise.resolve(data)});
    vi.stubGlobal('fetch', fetchMock);
    await getGrowingUnits();
    expect(fetchMock.mock.calls[0][0]).toBe('/growing-units');
  });
});

// ── getNotes ──────────────────────────────────────────────

describe('getNotes', () => {
  it('fetches /photos/{photoId}/notes', async () => {
    const fetchMock = mockFetch({body: []});
    vi.stubGlobal('fetch', fetchMock);
    await getNotes(42);
    expect(fetchMock.mock.calls[0][0]).toBe('/photos/42/notes');
  });
});

// ── updateNote ────────────────────────────────────────────

describe('updateNote', () => {
  it('sends PUT with JSON body to /notes/{noteId}', async () => {
    const fetchMock = mockFetch({body: {id: 3}});
    vi.stubGlobal('fetch', fetchMock);
    await updateNote(3, {note_text: 'updated'});
    expect(fetchMock.mock.calls[0][0]).toBe('/notes/3');
    expect(fetchMock.mock.calls[0][1].method).toBe('PUT');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({note_text: 'updated'});
  });
});

// ── createLocation ────────────────────────────────────────

describe('createLocation', () => {
  it('sends POST with JSON body to /locations', async () => {
    const fetchMock = mockFetch({body: {id: 1, name: 'Balcony'}});
    vi.stubGlobal('fetch', fetchMock);
    await createLocation({name: 'Balcony'});
    expect(fetchMock.mock.calls[0][0]).toBe('/locations');
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({name: 'Balcony'});
  });
});

// ── createGrowingUnit ─────────────────────────────────────

describe('createGrowingUnit', () => {
  it('sends POST with JSON body to /growing-units', async () => {
    const fetchMock = mockFetch({body: {id: 1}});
    vi.stubGlobal('fetch', fetchMock);
    await createGrowingUnit({name: 'Thai basil', unit_type: 'individual'});
    expect(fetchMock.mock.calls[0][0]).toBe('/growing-units');
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({name: 'Thai basil', unit_type: 'individual'});
  });
});

// ── createEvent ───────────────────────────────────────────

describe('createEvent', () => {
  it('sends POST with JSON body to /events', async () => {
    const fetchMock = mockFetch({body: {id: 1}});
    vi.stubGlobal('fetch', fetchMock);
    await createEvent({event_type: 'watered', photo_ids: [5]});
    expect(fetchMock.mock.calls[0][0]).toBe('/events');
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({event_type: 'watered', photo_ids: [5]});
  });
});

// ── getEvents ─────────────────────────────────────────────

describe('getEvents', () => {
  it('fetches /events and returns parsed JSON', async () => {
    const data = [{id: 1, event_type: 'watered'}];
    vi.stubGlobal('fetch', mockFetch({body: data}));
    await expect(getEvents()).resolves.toEqual(data);
  });

  it('fetches /events with no query params', async () => {
    const fetchMock = mockFetch({body: []});
    vi.stubGlobal('fetch', fetchMock);
    await getEvents();
    expect(fetchMock.mock.calls[0][0]).toBe('/events');
  });
});

// ── uploadPhoto ───────────────────────────────────────────

describe('uploadPhoto', () => {
  it('sends POST with FormData body to /manual-photos', async () => {
    const fetchMock = mockFetch({body: {id: 1}});
    vi.stubGlobal('fetch', fetchMock);
    const fd = new FormData();
    fd.append('image', new Blob(['bytes'], {type: 'image/jpeg'}), 'photo.jpg');
    await uploadPhoto(fd);
    expect(fetchMock.mock.calls[0][0]).toBe('/manual-photos');
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
    expect(fetchMock.mock.calls[0][1].body).toBe(fd);
  });

  it('does not set Content-Type header (browser sets it for FormData)', async () => {
    const fetchMock = mockFetch({body: {id: 1}});
    vi.stubGlobal('fetch', fetchMock);
    await uploadPhoto(new FormData());
    const opts = fetchMock.mock.calls[0][1];
    expect(opts.headers).toBeUndefined();
  });
});
