import { describe, it, expect } from 'vitest';
import { rotTransform, formatDate } from '@/utils.js';

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

describe('formatDate', () => {
  it('returns a non-empty string for a valid ISO date', () => {
    const result = formatDate('2024-01-15T10:30:00Z');
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });
});
