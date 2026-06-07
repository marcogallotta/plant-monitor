import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

test('note pin round-trip: placed at known fraction, persists after reload', async ({ page, request }) => {
  const resp = await request.post('/manual-photos', {
    multipart: {
      image: { name: 'pin-test.jpg', mimeType: 'image/jpeg', buffer: Buffer.concat([FIXTURE_JPG, Buffer.from(String(Math.random()))]) },
    },
  });
  expect(resp.status()).toBe(201);
  const { id: photoId } = await resp.json();

  let galleryReady = page.waitForResponse(
    r => /\/photos(\?|$)/.test(r.url()) && r.request().method() === 'GET',
  );
  await page.goto('/');
  await galleryReady;
  await page.locator(`.photo-card[data-id="${photoId}"] img`).click();
  const modal = page.locator('#modal');
  await expect(modal).toBeVisible();
  await page.waitForFunction(() => {
    const img = document.getElementById('modal-img');
    return img && img.complete && img.naturalWidth > 0;
  });

  await expect(modal.locator('.note-pin')).toHaveCount(0);

  const imgBox = await page.locator('#modal-img').boundingBox();
  await page.mouse.click(imgBox.x + imgBox.width * 0.3, imgBox.y + imgBox.height * 0.4);

  await expect(modal.locator('#note-panel')).not.toHaveClass(/hidden/);
  await page.locator('#note-text').fill('geometry test note');
  await page.locator('#note-save').click();

  await expect(modal.locator('.note-pin')).toHaveCount(1);
  await assertPinAt(page, 0.3, 0.4);

  galleryReady = page.waitForResponse(
    r => /\/photos(\?|$)/.test(r.url()) && r.request().method() === 'GET',
  );
  await page.reload();
  await galleryReady;
  await page.locator(`.photo-card[data-id="${photoId}"] img`).click();
  await expect(modal).toBeVisible();
  await page.waitForFunction(() => {
    const img = document.getElementById('modal-img');
    return img && img.complete && img.naturalWidth > 0;
  });

  await expect(modal.locator('.note-pin')).toHaveCount(1);
  await assertPinAt(page, 0.3, 0.4);
});

async function assertPinAt(page, expectedX, expectedY) {
  const pinBox = await page.locator('.note-pin').first().boundingBox();
  const imgBox = await page.locator('#modal-img').boundingBox();
  const actualX = (pinBox.x + pinBox.width / 2 - imgBox.x) / imgBox.width;
  const actualY = (pinBox.y + pinBox.height / 2 - imgBox.y) / imgBox.height;
  expect(actualX).toBeCloseTo(expectedX, 1);
  expect(actualY).toBeCloseTo(expectedY, 1);
}
