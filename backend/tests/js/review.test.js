import { vi, describe, it, expect, beforeEach } from 'vitest';

// Minimal DOM the module needs
document.body.innerHTML = `
  <div id="tab-review" class="tab-content active"></div>
  <div id="review-counter"></div>
  <div id="review-container"></div>
  <div id="review-status"></div>
`;

const { reviewKeydown } = await import('@/review.js');

describe('reviewKeydown modifier guard', () => {
  let resolveCall;

  beforeEach(() => {
    resolveCall = null;
    // Spy on window.reviewResolve if wired, but the module calls its own
    // reviewResolve internally — we verify via no side-effects instead.
  });

  function makeEvent(key, mods = {}) {
    const prevented = { value: false };
    return {
      key,
      ctrlKey:  mods.ctrl  ?? false,
      metaKey:  mods.meta  ?? false,
      altKey:   mods.alt   ?? false,
      target:   { tagName: 'BODY', isContentEditable: false },
      preventDefault: () => { prevented.value = true; },
      _prevented: prevented,
    };
  }

  it('Ctrl+R does not preventDefault', () => {
    const e = makeEvent('r', { ctrl: true });
    reviewKeydown(e);
    expect(e._prevented.value).toBe(false);
  });

  it('Cmd+R does not preventDefault', () => {
    const e = makeEvent('r', { meta: true });
    reviewKeydown(e);
    expect(e._prevented.value).toBe(false);
  });

  it('plain R does preventDefault', () => {
    const e = makeEvent('r');
    reviewKeydown(e);
    expect(e._prevented.value).toBe(true);
  });

  it('Ctrl+D does not preventDefault', () => {
    const e = makeEvent('d', { ctrl: true });
    reviewKeydown(e);
    expect(e._prevented.value).toBe(false);
  });

  it('Alt+A does not preventDefault', () => {
    const e = makeEvent('a', { alt: true });
    reviewKeydown(e);
    expect(e._prevented.value).toBe(false);
  });
});
