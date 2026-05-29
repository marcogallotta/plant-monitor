import { describe, it, expect } from 'vitest';
import { rotTransform, orientedUrl, formatDate, populateSelect } from '@/utils.js';

describe('rotTransform', () => {
  it('returns empty string for 0 or falsy', () => {
    expect(rotTransform(0)).toBe('');
    expect(rotTransform(null)).toBe('');
  });

  it('returns rotate only for 180', () => {
    expect(rotTransform(180)).toBe('rotate(180deg)');
  });

  it('adds scale for 90 and 270', () => {
    expect(rotTransform(90)).toBe('rotate(90deg) scale(1.778)');
    expect(rotTransform(270)).toBe('rotate(270deg) scale(1.778)');
  });
});

describe('orientedUrl', () => {
  it('appends oriented flag and rotation cache-buster', () => {
    expect(orientedUrl({url: '/photos/a.jpg', rotation: 90})).toBe('/photos/a.jpg?oriented=1&v=90');
  });

  it('uses v=0 when rotation is missing', () => {
    expect(orientedUrl({url: '/photos/a.jpg'})).toBe('/photos/a.jpg?oriented=1&v=0');
  });

  it('uses & when the url already has a query string', () => {
    expect(orientedUrl({url: '/photos/a.jpg?token=abc', rotation: 180}))
      .toBe('/photos/a.jpg?token=abc&oriented=1&v=180');
  });
});

describe('formatDate', () => {
  it('returns a non-empty string for a valid ISO date', () => {
    const result = formatDate('2024-01-15T10:30:00Z');
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });
});

describe('populateSelect', () => {
  it('adds a blank option followed by items for a single-select', () => {
    document.body.innerHTML = '<select id="sel"></select>';
    populateSelect('sel', [{id: 1, name: 'Foo'}, {id: 2, name: 'Bar'}], 'All');
    const sel = document.getElementById('sel');
    expect(sel.options.length).toBe(3);
    expect(sel.options[0].value).toBe('');
    expect(sel.options[0].textContent).toBe('All');
    expect(sel.options[1].value).toBe('1');
    expect(sel.options[1].textContent).toBe('Foo');
    expect(sel.options[2].value).toBe('2');
  });

  it('omits blank option for multi-select', () => {
    document.body.innerHTML = '<select id="sel" multiple></select>';
    populateSelect('sel', [{id: 1, name: 'Foo'}], null);
    const sel = document.getElementById('sel');
    expect(sel.options.length).toBe(1);
    expect(sel.options[0].value).toBe('1');
  });

  it('clears existing options before repopulating', () => {
    document.body.innerHTML = '<select id="sel"><option value="old">Old</option></select>';
    populateSelect('sel', [{id: 1, name: 'New'}], 'All');
    const values = Array.from(document.getElementById('sel').options).map(o => o.value);
    expect(values).not.toContain('old');
    expect(values).toContain('1');
  });

  it('handles an empty items array', () => {
    document.body.innerHTML = '<select id="sel"></select>';
    populateSelect('sel', [], 'All');
    const sel = document.getElementById('sel');
    expect(sel.options.length).toBe(1);
    expect(sel.options[0].value).toBe('');
  });
});
