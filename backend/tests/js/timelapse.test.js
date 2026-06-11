import { vi, describe, it, expect, beforeAll, beforeEach, afterEach } from 'vitest';

let tlInit, tlPrev, tlNext, tlPlayPause;
let state;

// Newest-first, matching the API's captured_at DESC order.
// tlFrames() reverses this so frame 0 = oldest (a.jpg) and playback is chronological.
const PHOTOS = [
  {id: 3, url: '/photos/c.jpg', captured_at: '2026-01-03T10:00:00Z'},
  {id: 2, url: '/photos/b.jpg', captured_at: '2026-01-02T10:00:00Z'},
  {id: 1, url: '/photos/a.jpg', captured_at: '2026-01-01T10:00:00Z'},
];

beforeAll(async () => {
  document.body.innerHTML = `
    <div id="tl-empty" style="display:none"></div>
    <img id="tl-img" style="display:none" src="">
    <canvas id="tl-canvas" style="display:none"></canvas>
    <div id="tl-label" style="display:none"></div>
    <span id="tl-counter"></span>
    <button id="tl-prev" disabled></button>
    <button id="tl-play" disabled>▶ Play</button>
    <button id="tl-next" disabled></button>
    <input id="tl-speed" type="range" value="2">
    <span id="tl-fps"></span>
    <label id="tl-stab-label" style="display:none"><input type="checkbox" id="tl-stab" checked></label>
  `;

  ({tlInit, tlPrev, tlNext, tlPlayPause} = await import('@/timelapse.js'));
  ({state} = await import('@/state.js'));
});

beforeEach(() => {
  state.allPhotos = PHOTOS.slice();
  state.tlIndex = 0;
  if (state.tlTimer) { clearInterval(state.tlTimer); state.tlTimer = null; }
  document.getElementById('tl-play').textContent = '▶ Play';
  document.getElementById('tl-play').classList.remove('active');
  document.getElementById('tl-stab').checked = true;
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  if (state.tlTimer) { clearInterval(state.tlTimer); state.tlTimer = null; }
});

// ── tlInit ────────────────────────────────────────────────

describe('tlInit', () => {
  it('shows empty state and disables buttons when allPhotos is empty', () => {
    state.allPhotos = [];
    tlInit();
    expect(document.getElementById('tl-empty').style.display).toBe('block');
    expect(document.getElementById('tl-img').style.display).toBe('none');
    expect(document.getElementById('tl-prev').disabled).toBe(true);
    expect(document.getElementById('tl-play').disabled).toBe(true);
    expect(document.getElementById('tl-next').disabled).toBe(true);
  });

  it('shows first frame and enables buttons when photos exist', () => {
    state.allPhotos = PHOTOS;
    tlInit();
    expect(document.getElementById('tl-empty').style.display).toBe('none');
    expect(document.getElementById('tl-img').style.display).toBe('block');
    expect(document.getElementById('tl-img').src).toContain(PHOTOS[2].url); // oldest = first chronological frame
    expect(document.getElementById('tl-prev').disabled).toBe(false);
    expect(document.getElementById('tl-play').disabled).toBe(false);
    expect(document.getElementById('tl-next').disabled).toBe(false);
  });

  it('resets tlIndex to 0', () => {
    state.tlIndex = 2;
    tlInit();
    expect(state.tlIndex).toBe(0);
  });

  it('shows the counter as "1 / N"', () => {
    state.allPhotos = PHOTOS;
    tlInit();
    expect(document.getElementById('tl-counter').textContent).toBe('1 / 3');
  });
});

// ── night-frame filtering when stabilizing ────────────────

describe('stabilized timelapse skips night frames', () => {
  const M = [1, 0, 0, 0, 1, 0];
  const MIXED = [
    {id: 1, url: '/photos/day1.jpg',   captured_at: '2026-01-01T10:00:00Z', stab_matrix: M, stab_ref_w: 1600, stab_ref_h: 900},
    {id: 2, url: '/photos/night.jpg',  captured_at: '2026-01-01T22:00:00Z'},  // no transform = night
    {id: 3, url: '/photos/day2.jpg',   captured_at: '2026-01-02T10:00:00Z', stab_matrix: M, stab_ref_w: 1600, stab_ref_h: 900},
  ];

  it('plays only stabilizable frames and the night one is dropped', () => {
    state.allPhotos = MIXED.slice();
    document.getElementById('tl-stab').checked = true;
    tlInit();
    expect(document.getElementById('tl-stab-label').style.display).toBe('');
    expect(document.getElementById('tl-counter').textContent).toBe('1 / 2');
    tlNext();
    expect(document.getElementById('tl-counter').textContent).toBe('2 / 2');
  });

  it('keeps the same frame set when stabilization is toggled off (only warp changes)', () => {
    state.allPhotos = MIXED.slice();
    document.getElementById('tl-stab').checked = false;
    tlInit();
    // Membership is stable across the toggle: the night frame stays dropped, the
    // toggle only controls warping — it must not re-introduce filtered-out frames.
    expect(document.getElementById('tl-counter').textContent).toBe('1 / 2');
  });
});

// ── tlNext ────────────────────────────────────────────────

describe('tlNext', () => {
  it('advances the index', () => {
    state.allPhotos = PHOTOS;
    state.tlIndex = 0;
    tlNext();
    expect(state.tlIndex).toBe(1);
    expect(document.getElementById('tl-img').src).toContain(PHOTOS[1].url);
  });

  it('wraps from the last photo back to the first', () => {
    state.allPhotos = PHOTOS;
    state.tlIndex = 2;
    tlNext();
    expect(state.tlIndex).toBe(0);
  });
});

// ── tlPrev ────────────────────────────────────────────────

describe('tlPrev', () => {
  it('steps back the index', () => {
    state.allPhotos = PHOTOS;
    state.tlIndex = 2;
    tlPrev();
    expect(state.tlIndex).toBe(1);
  });

  it('wraps from index 0 to the last photo', () => {
    state.allPhotos = PHOTOS;
    state.tlIndex = 0;
    tlPrev();
    expect(state.tlIndex).toBe(2);
  });
});

// ── tlPlayPause ───────────────────────────────────────────

describe('tlPlayPause', () => {
  it('starts a timer and changes button text to Pause', () => {
    state.allPhotos = PHOTOS;
    tlPlayPause();
    expect(state.tlTimer).not.toBeNull();
    expect(document.getElementById('tl-play').textContent).toContain('Pause');
    expect(document.getElementById('tl-play').classList.contains('active')).toBe(true);
  });

  it('calling again stops the timer and resets button text', () => {
    state.allPhotos = PHOTOS;
    tlPlayPause();
    tlPlayPause();
    expect(state.tlTimer).toBeNull();
    expect(document.getElementById('tl-play').textContent).toContain('Play');
    expect(document.getElementById('tl-play').classList.contains('active')).toBe(false);
  });

  it('advances through photos on each interval tick', () => {
    state.allPhotos = PHOTOS;
    state.tlIndex = 0;
    const fps = parseInt(document.getElementById('tl-speed').value, 10);
    tlPlayPause();
    vi.advanceTimersByTime(1000 / fps);
    expect(state.tlIndex).toBe(1);
    vi.advanceTimersByTime(1000 / fps);
    expect(state.tlIndex).toBe(2);
  });
});
