import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getLocations, getPhotos, updatePhoto, createNote, deleteNote } from '@/api.js';

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
  it('fetches /photos with no query string when params are empty', async () => {
    const fetchMock = mockFetch({body: []});
    vi.stubGlobal('fetch', fetchMock);
    await getPhotos({});
    expect(fetchMock.mock.calls[0][0]).toBe('/photos');
  });

  it('builds a query string from all provided params', async () => {
    const fetchMock = mockFetch({body: []});
    vi.stubGlobal('fetch', fetchMock);
    await getPhotos({source: 'pi', ptype: 'overview', location: '1', unit: '2'});
    const url = fetchMock.mock.calls[0][0];
    expect(url).toContain('source=pi');
    expect(url).toContain('photo_type=overview');
    expect(url).toContain('location_id=1');
    expect(url).toContain('growing_unit_id=2');
  });

  it('omits params that are empty/falsy', async () => {
    const fetchMock = mockFetch({body: []});
    vi.stubGlobal('fetch', fetchMock);
    await getPhotos({source: '', ptype: null, location: undefined, unit: ''});
    expect(fetchMock.mock.calls[0][0]).toBe('/photos');
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
