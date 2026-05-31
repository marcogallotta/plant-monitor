import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

async function uploadAndOpenModal(page, request, filename) {
  const resp = await request.post('/manual-photos', {
    multipart: {
      image: { name: filename, mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
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

test('dragstart during pan clears pan state — prevents stuck-grabbing bug', async ({ page, request }) => {
  await uploadAndOpenModal(page, request, 'pan-stuck-test.jpg');

  const vpBox = await page.locator('#zoom-viewport').boundingBox();
  const cx = vpBox.x + vpBox.width  / 2;
  const cy = vpBox.y + vpBox.height / 2;

  // Zoom in so panning is enabled
  await page.mouse.move(cx, cy);
  for (let i = 0; i < 5; i++) {
    await page.mouse.wheel(0, -120);
  }
  await page.waitForFunction(() => {
    const wrap = document.getElementById('modal-img-wrap');
    const m = wrap && wrap.style.transform.match(/scale\(([^)]+)\)/);
    return m && parseFloat(m[1]) > 1.5;
  });

  // Start panning
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx - 10, cy, { steps: 3 });
  await expect(page.locator('#zoom-viewport')).toHaveClass(/grabbing/);

  // Simulate Brave initiating a native image drag, which steals the pointer so
  // document mouseup is never delivered. The pan handler must clean up on dragstart.
  await page.evaluate(() => {
    document.getElementById('modal-img').dispatchEvent(
      new DragEvent('dragstart', { bubbles: true }),
    );
  });

  // Pan state must be cleared — if it isn't, the grabbing cursor stays and every
  // subsequent mousemove will keep scrolling the image.
  await expect(page.locator('#zoom-viewport')).not.toHaveClass(/grabbing/);

  // Confirm: a mousemove after dragstart does NOT pan the image.
  const imgBoxBefore = await page.locator('#modal-img').boundingBox();
  await page.mouse.move(cx - 60, cy - 40, { steps: 5 });
  const imgBoxAfter = await page.locator('#modal-img').boundingBox();
  expect(imgBoxAfter.x).toBeCloseTo(imgBoxBefore.x, 0);
  expect(imgBoxAfter.y).toBeCloseTo(imgBoxBefore.y, 0);

  await page.mouse.up();
});
