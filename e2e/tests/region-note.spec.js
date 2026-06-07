import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

// Non-square dimensions matter: the suite exists to catch real layout geometry
// bugs that only appear in a real browser. A square fixture would silently hide
// rotation/aspect-ratio regressions. Assert the fixture stays 400×300.
{
  const { width, height } = jpegDimensions(FIXTURE_JPG);
  if (width !== 400 || height !== 300) {
    throw new Error(`fixture must be 400×300 but is ${width}×${height}`);
  }
}

function jpegDimensions(buf) {
  let i = 2;
  while (i < buf.length - 8) {
    if (buf[i] !== 0xFF) break;
    const marker = buf[i + 1];
    const len = (buf[i + 2] << 8) | buf[i + 3];
    if (marker >= 0xC0 && marker <= 0xCF && marker !== 0xC4 && marker !== 0xC8 && marker !== 0xCC) {
      return { height: (buf[i + 5] << 8) | buf[i + 6], width: (buf[i + 7] << 8) | buf[i + 8] };
    }
    i += 2 + len;
  }
  throw new Error('JPEG SOF marker not found');
}

async function uploadAndOpenModal(page, request, filename) {
  const resp = await request.post('/manual-photos', {
    multipart: {
      image: { name: filename, mimeType: 'image/jpeg', buffer: Buffer.concat([FIXTURE_JPG, Buffer.from(String(Math.random()))]) },
    },
  });
  expect(resp.status()).toBe(201);
  const { id: photoId } = await resp.json();

  const galleryReady = page.waitForResponse(
    r => /\/photos(\?|$)/.test(r.url()) && r.request().method() === 'GET',
  );
  await page.goto('/');
  await galleryReady;
  await page.locator(`.photo-card[data-id="${photoId}"] img`).click();
  await expect(page.locator('#modal')).toBeVisible();
  await page.waitForFunction(() => {
    const img = document.getElementById('modal-img');
    return img && img.complete && img.naturalWidth > 0;
  });
  return photoId;
}

async function shiftDrag(page, x1, y1, x2, y2) {
  await page.keyboard.down('Shift');
  try {
    await page.mouse.move(x1, y1);
    await page.mouse.down();
    await page.mouse.move(x2, y2, { steps: 5 });
    await page.mouse.up();
  } finally {
    await page.keyboard.up('Shift');
  }
}

// Asserts that .note-rect spans the expected fraction of the visual image.
// Uses getBoundingClientRect on both elements — works correctly at any zoom/pan
// because both are inside the same CSS-transformed wrapper.
async function assertRectAt(page, rx1, ry1, rx2, ry2) {
  const rectBox = await page.locator('.note-rect').first().boundingBox();
  const imgBox  = await page.locator('#modal-img').boundingBox();
  expect((rectBox.x - imgBox.x) / imgBox.width).toBeCloseTo(rx1, 1);
  expect((rectBox.y - imgBox.y) / imgBox.height).toBeCloseTo(ry1, 1);
  expect((rectBox.x + rectBox.width  - imgBox.x) / imgBox.width).toBeCloseTo(rx2, 1);
  expect((rectBox.y + rectBox.height - imgBox.y) / imgBox.height).toBeCloseTo(ry2, 1);
}

test('shift-drag creates region note at expected visual position and persists after reload', async ({ page, request }) => {
  const photoId = await uploadAndOpenModal(page, request, 'region-test.jpg');
  await expect(page.locator('#modal .note-rect')).toHaveCount(0);

  const imgBox = await page.locator('#modal-img').boundingBox();
  await shiftDrag(
    page,
    imgBox.x + imgBox.width  * 0.2, imgBox.y + imgBox.height * 0.2,
    imgBox.x + imgBox.width  * 0.7, imgBox.y + imgBox.height * 0.65,
  );

  await expect(page.locator('#note-panel-title')).toHaveText('New region note');
  await page.locator('#note-text').fill('region geometry test');
  await page.locator('#note-save').click();

  await expect(page.locator('#modal .note-rect')).toHaveCount(1);
  await assertRectAt(page, 0.2, 0.2, 0.7, 0.65);

  const galleryReady = page.waitForResponse(
    r => /\/photos(\?|$)/.test(r.url()) && r.request().method() === 'GET',
  );
  await page.reload();
  await galleryReady;
  await page.locator(`.photo-card[data-id="${photoId}"] img`).click();
  await expect(page.locator('#modal')).toBeVisible();
  await page.waitForFunction(() => {
    const img = document.getElementById('modal-img');
    return img && img.complete && img.naturalWidth > 0;
  });
  await expect(page.locator('#modal .note-rect')).toHaveCount(1);
  await assertRectAt(page, 0.2, 0.2, 0.7, 0.65);
});

test('dragging an existing region note repositions it and persists after reload', async ({ page, request }) => {
  const photoId = await uploadAndOpenModal(page, request, 'region-move-test.jpg');

  // Create a region note at 0.2,0.2 → 0.5,0.5
  const imgBox = await page.locator('#modal-img').boundingBox();
  await shiftDrag(
    page,
    imgBox.x + imgBox.width  * 0.2, imgBox.y + imgBox.height * 0.2,
    imgBox.x + imgBox.width  * 0.5, imgBox.y + imgBox.height * 0.5,
  );
  await page.locator('#note-text').fill('movable region');
  await page.locator('#note-save').click();
  await expect(page.locator('#modal .note-rect')).toHaveCount(1);
  await assertRectAt(page, 0.2, 0.2, 0.5, 0.5);

  // Plain-drag (no shift) the rect by +0.2 in x and +0.15 in y, starting from
  // inside the rect (its centre ≈ 0.35, 0.35). Wait for the PUT and the GET that
  // loadNotes() fires afterwards, so the pins have re-rendered before measuring.
  const moveResp = page.waitForResponse(
    r => /\/notes\/\d+$/.test(r.url()) && r.request().method() === 'PUT',
  );
  const notesReloaded = page.waitForResponse(
    r => /\/photos\/\d+\/notes$/.test(r.url()) && r.request().method() === 'GET',
  );
  await page.mouse.move(imgBox.x + imgBox.width * 0.35, imgBox.y + imgBox.height * 0.35);
  await page.mouse.down();
  await page.mouse.move(imgBox.x + imgBox.width * 0.55, imgBox.y + imgBox.height * 0.50, { steps: 5 });
  await page.mouse.up();
  await moveResp;
  await notesReloaded;

  await expect(page.locator('#modal .note-rect')).toHaveCount(1);
  await assertRectAt(page, 0.4, 0.35, 0.7, 0.65);

  // Persists across reload
  const galleryReady = page.waitForResponse(
    r => /\/photos(\?|$)/.test(r.url()) && r.request().method() === 'GET',
  );
  await page.reload();
  await galleryReady;
  await page.locator(`.photo-card[data-id="${photoId}"] img`).click();
  await expect(page.locator('#modal')).toBeVisible();
  await page.waitForFunction(() => {
    const img = document.getElementById('modal-img');
    return img && img.complete && img.naturalWidth > 0;
  });
  await expect(page.locator('#modal .note-rect')).toHaveCount(1);
  await assertRectAt(page, 0.4, 0.35, 0.7, 0.65);
});

test('shift-drag region note after zoom and pan lands at correct visual fraction', async ({ page, request }) => {
  await uploadAndOpenModal(page, request, 'zoom-region-test.jpg');

  // Zoom in ~2x at the viewport centre (1.15^5 ≈ 2.01)
  const vpBox = await page.locator('#zoom-viewport').boundingBox();
  const cx = vpBox.x + vpBox.width  / 2;
  const cy = vpBox.y + vpBox.height / 2;
  await page.mouse.move(cx, cy);
  for (let i = 0; i < 5; i++) {
    await page.mouse.wheel(0, -120);
  }
  await page.waitForFunction(() => {
    const wrap = document.getElementById('modal-img-wrap');
    const m = wrap && wrap.style.transform.match(/scale\(([^)]+)\)/);
    return m && parseFloat(m[1]) > 1.5;
  });

  // Pan the image left/up — only allowed when zoom > 1
  const imgBoxBeforePan = await page.locator('#modal-img').boundingBox();
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx - 40, cy - 30, { steps: 5 });
  await page.mouse.up();
  const imgBoxAfterPan = await page.locator('#modal-img').boundingBox();
  expect(imgBoxAfterPan.x).toBeLessThan(imgBoxBeforePan.x);
  expect(imgBoxAfterPan.y).toBeLessThan(imgBoxBeforePan.y);

  // At zoom>1, imgBox (from getBoundingClientRect) extends beyond #zoom-viewport.
  // Clip drag positions to the visible intersection so the shift+mousedown fires
  // on #zoom-viewport. Expected fractions are still computed from imgBox because
  // imgCoordsFromEvent normalises against getBoundingClientRect internally.
  const imgBox = await page.locator('#modal-img').boundingBox();
  const visX1 = Math.max(imgBox.x, vpBox.x);
  const visY1 = Math.max(imgBox.y, vpBox.y);
  const visX2 = Math.min(imgBox.x + imgBox.width,  vpBox.x + vpBox.width);
  const visY2 = Math.min(imgBox.y + imgBox.height, vpBox.y + vpBox.height);

  const dragX1 = visX1 + (visX2 - visX1) * 0.25;
  const dragY1 = visY1 + (visY2 - visY1) * 0.25;
  const dragX2 = visX1 + (visX2 - visX1) * 0.75;
  const dragY2 = visY1 + (visY2 - visY1) * 0.75;

  const expX1 = (dragX1 - imgBox.x) / imgBox.width;
  const expY1 = (dragY1 - imgBox.y) / imgBox.height;
  const expX2 = (dragX2 - imgBox.x) / imgBox.width;
  const expY2 = (dragY2 - imgBox.y) / imgBox.height;

  await shiftDrag(page, dragX1, dragY1, dragX2, dragY2);

  await expect(page.locator('#note-panel-title')).toHaveText('New region note');
  await page.locator('#note-text').fill('zoom-pan region test');
  await page.locator('#note-save').click();

  await expect(page.locator('#modal .note-rect')).toHaveCount(1);
  await assertRectAt(page, expX1, expY1, expX2, expY2);
});
