import { vi, describe, it, expect, beforeAll, beforeEach, afterEach } from 'vitest';
import { makeFetchMock } from './fetchHelper.js';

let renderLabelSection, handleLabelInput, handleLabelKeydown;
let state;

const PHOTO = {
  id: 5, url: '/photos/test.jpg', filename: 'test.jpg',
  captured_at: '2026-01-01T10:00:00Z', rotation: 0,
  source: 'pi', photo_type: null, growing_units: [],
  labels: [], original_filename: null, location_id: null,
};

beforeAll(async () => {
  document.body.innerHTML = `
    <div id="label-assigned" class="label-chips"></div>
    <div style="position:relative">
      <input id="label-input" type="text">
      <div id="label-dropdown" class="hidden"></div>
    </div>
    <span id="label-status"></span>
  `;

  ({renderLabelSection, handleLabelInput, handleLabelKeydown} =
    await import('@/labels.js'));
  ({state} = await import('@/state.js'));
});

let fetchMock;

beforeEach(() => {
  fetchMock = makeFetchMock([
    {method: 'POST', url: /^\/photos\/\d+\/labels\/\d+$/, body: {...PHOTO, labels: [{id: 1, name: 'aphids'}]}},
    {method: 'DELETE', url: /^\/photos\/\d+\/labels\/\d+$/, ok: true},
    {method: 'POST', url: '/labels', body: {id: 99, name: 'rust'}},
  ]);
  vi.stubGlobal('fetch', fetchMock);
  state.allPhotos = [PHOTO];
  state.allLabels = [{id: 1, name: 'aphids'}, {id: 2, name: 'yellowing'}];
  state.currentIndex = 0;
  state.currentPhotoId = null;
  document.getElementById('label-input').value = '';
  document.getElementById('label-dropdown').innerHTML = '';
  document.getElementById('label-dropdown').classList.add('hidden');
  document.getElementById('label-status').textContent = '';
});

afterEach(() => vi.unstubAllGlobals());

// ── renderLabelSection ────────────────────────────────────

describe('renderLabelSection', () => {
  it('renders one chip per assigned label', () => {
    renderLabelSection({labels: [{id: 1, name: 'aphids'}, {id: 2, name: 'yellowing'}]});
    expect(document.getElementById('label-assigned').querySelectorAll('.label-chip').length).toBe(2);
  });

  it('renders chip text from label name (underscores → spaces)', () => {
    renderLabelSection({labels: [{id: 1, name: 'new_growth'}]});
    const chip = document.getElementById('label-assigned').querySelector('.label-chip');
    expect(chip.textContent).toContain('new growth');
  });

  it('renders a remove button per chip', () => {
    renderLabelSection({labels: [{id: 1, name: 'aphids'}]});
    expect(document.getElementById('label-assigned').querySelectorAll('.label-chip-remove').length).toBe(1);
  });

  it('renders no chips when labels is empty', () => {
    renderLabelSection({labels: []});
    expect(document.getElementById('label-assigned').querySelectorAll('.label-chip').length).toBe(0);
  });

  it('clears the label input', () => {
    document.getElementById('label-input').value = 'something';
    renderLabelSection({labels: []});
    expect(document.getElementById('label-input').value).toBe('');
  });

  it('hides the dropdown', () => {
    document.getElementById('label-dropdown').classList.remove('hidden');
    renderLabelSection({labels: []});
    expect(document.getElementById('label-dropdown').classList.contains('hidden')).toBe(true);
  });
});

// ── handleLabelInput ──────────────────────────────────────

describe('handleLabelInput', () => {
  beforeEach(() => {
    state.currentIndex = 0;
    state.allPhotos = [{...PHOTO, labels: []}];
    state.allLabels = [{id: 1, name: 'aphids'}, {id: 2, name: 'yellowing'}];
  });

  it('hides dropdown when input is empty', () => {
    document.getElementById('label-input').value = '';
    handleLabelInput();
    expect(document.getElementById('label-dropdown').classList.contains('hidden')).toBe(true);
  });

  it('shows matching labels in dropdown', () => {
    document.getElementById('label-input').value = 'aph';
    handleLabelInput();
    const items = document.getElementById('label-dropdown').querySelectorAll('.label-dropdown-item');
    expect(items.length).toBeGreaterThan(0);
    expect(items[0].textContent).toContain('aphids');
  });

  it('shows create option when no exact match', () => {
    document.getElementById('label-input').value = 'rust';
    handleLabelInput();
    const createItem = document.getElementById('label-dropdown').querySelector('.label-create');
    expect(createItem).not.toBeNull();
    expect(createItem.textContent).toContain('rust');
  });

  it('does not show create option when exact match exists', () => {
    document.getElementById('label-input').value = 'aphids';
    handleLabelInput();
    const createItem = document.getElementById('label-dropdown').querySelector('.label-create');
    expect(createItem).toBeNull();
  });

  it('does not show already-assigned labels in dropdown', () => {
    state.allPhotos = [{...PHOTO, labels: [{id: 1, name: 'aphids'}]}];
    document.getElementById('label-input').value = 'aph';
    handleLabelInput();
    const items = document.getElementById('label-dropdown').querySelectorAll('.label-dropdown-item:not(.label-create)');
    expect(items.length).toBe(0);
  });
});

// ── handleLabelKeydown ────────────────────────────────────

describe('handleLabelKeydown', () => {
  beforeEach(() => {
    state.currentPhotoId = 5;
    state.currentIndex = 0;
    state.allPhotos = [{...PHOTO, labels: []}];
    state.allLabels = [{id: 1, name: 'aphids'}];
    document.getElementById('label-input').value = '';
  });

  it('ignores keys other than Enter', async () => {
    document.getElementById('label-input').value = 'aphids';
    await handleLabelKeydown({key: 'Tab', preventDefault: vi.fn()});
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does nothing when input is empty', async () => {
    document.getElementById('label-input').value = '';
    await handleLabelKeydown({key: 'Enter', preventDefault: vi.fn()});
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('POSTs to /photos/5/labels/1 for an existing label on Enter', async () => {
    document.getElementById('label-input').value = 'aphids';
    await handleLabelKeydown({key: 'Enter', preventDefault: vi.fn()});
    expect(fetchMock).toHaveBeenCalledWith('/photos/5/labels/1', expect.objectContaining({method: 'POST'}));
  });

  it('POSTs /labels then /photos/5/labels/99 for a new label on Enter', async () => {
    document.getElementById('label-input').value = 'rust';
    await handleLabelKeydown({key: 'Enter', preventDefault: vi.fn()});
    const labelCall = fetchMock.mock.calls.find(([u, o]) => u === '/labels' && o?.method === 'POST');
    expect(JSON.parse(labelCall[1].body)).toEqual({name: 'rust'});
    expect(fetchMock).toHaveBeenCalledWith('/photos/5/labels/99', expect.objectContaining({method: 'POST'}));
  });

  it('adds new label to state.allLabels after creation', async () => {
    document.getElementById('label-input').value = 'rust';
    await handleLabelKeydown({key: 'Enter', preventDefault: vi.fn()});
    expect(state.allLabels.some(function(l) { return l.name === 'rust'; })).toBe(true);
  });

  it('calls preventDefault on Enter', async () => {
    const preventDefault = vi.fn();
    document.getElementById('label-input').value = 'aphids';
    await handleLabelKeydown({key: 'Enter', preventDefault});
    expect(preventDefault).toHaveBeenCalled();
  });
});
