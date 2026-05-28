import { describe, it, expect } from 'vitest';
import { CARE_ACTION_TYPES, buildEventBody } from '@/events.js';

// ── CARE_ACTION_TYPES ─────────────────────────────────────

describe('CARE_ACTION_TYPES', () => {
  it('contains exactly the 7 expected types', () => {
    expect(CARE_ACTION_TYPES).toHaveLength(7);
    expect(CARE_ACTION_TYPES).toEqual(
      expect.arrayContaining(['fed_liquid', 'fed_worm_castings', 'watered', 'harvested', 'potted_up', 'propagated', 'other'])
    );
  });
});

// ── buildEventBody ────────────────────────────────────────

describe('buildEventBody', () => {
  it('always includes event_type', () => {
    expect(buildEventBody('watered', '', '', [], '').event_type).toBe('watered');
  });

  it('converts at to ISO string when provided', () => {
    const body = buildEventBody('watered', '2026-05-27T10:00', '', [], '');
    expect(body.event_at).toMatch(/^2026-05-27T/);
  });

  it('omits event_at when empty', () => {
    expect(buildEventBody('watered', '', '', [], '')).not.toHaveProperty('event_at');
  });

  it('includes location_id as integer when provided', () => {
    expect(buildEventBody('watered', '', '3', [], '').location_id).toBe(3);
  });

  it('omits location_id when empty', () => {
    expect(buildEventBody('watered', '', '', [], '')).not.toHaveProperty('location_id');
  });

  it('includes growing_unit_ids when provided', () => {
    expect(buildEventBody('watered', '', '', [1, 2], '').growing_unit_ids).toEqual([1, 2]);
  });

  it('omits growing_unit_ids when array is empty', () => {
    expect(buildEventBody('watered', '', '', [], '')).not.toHaveProperty('growing_unit_ids');
  });

  it('includes note_text when provided', () => {
    expect(buildEventBody('harvested', '', '', [], 'big harvest').note_text).toBe('big harvest');
  });

  it('omits note_text when empty', () => {
    expect(buildEventBody('watered', '', '', [], '')).not.toHaveProperty('note_text');
  });
});
