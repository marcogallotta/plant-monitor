import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

async function uploadPhoto(request, filename) {
  const resp = await request.post('/manual-photos', {
    multipart: {
      image: { name: filename, mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
    },
  });
  expect(resp.status()).toBe(201);
  return (await resp.json()).id;
}

async function gotoGallery(page) {
  const galleryReady = page.waitForResponse(
    r => /\/photos(\?|$)/.test(r.url()) && r.request().method() === 'GET',
  );
  await page.goto('/');
  await galleryReady;
}

test('modal open, prev/next navigation, close', async ({ page }) => {
  await gotoGallery(page);

  // Seeded photos are always present. Click whichever is first in the grid —
  // it has index 0, so prev must be disabled.
  await page.locator('.photo-card').first().locator('img').click();
  const modal = page.locator('#modal');
  await expect(modal).toBeVisible();
  await page.waitForFunction(() => {
    const img = document.getElementById('modal-img');
    return img && img.complete && img.naturalWidth > 0;
  });

  // First in grid → prev disabled, next enabled
  await expect(page.locator('#modal-prev')).toBeDisabled();
  await expect(page.locator('#modal-next')).toBeEnabled();

  // Navigate to next photo
  const srcBefore = await page.locator('#modal-img').getAttribute('src');
  await page.locator('#modal-next').click();
  await page.waitForFunction(() => {
    const img = document.getElementById('modal-img');
    return img && img.complete && img.naturalWidth > 0;
  });
  const srcAfter = await page.locator('#modal-img').getAttribute('src');
  expect(srcAfter).not.toBe(srcBefore);
  await expect(page.locator('#modal-prev')).toBeEnabled();

  // Navigate back
  await page.locator('#modal-prev').click();
  await page.waitForFunction(() => {
    const img = document.getElementById('modal-img');
    return img && img.complete && img.naturalWidth > 0;
  });
  expect(await page.locator('#modal-img').getAttribute('src')).toBe(srcBefore);

  // Close
  await page.locator('.modal-close').click();
  await expect(modal).toHaveClass(/hidden/);
});

test('A/B select loads compare slots; toggle flicker switches label', async ({ page, request }) => {
  const [idA, idB] = await Promise.all([
    uploadPhoto(request, 'flicker-a.jpg'),
    uploadPhoto(request, 'flicker-b.jpg'),
  ]);

  await gotoGallery(page);

  // Toggle and Auto are disabled until both slots are filled
  await expect(page.locator('#btn-toggle')).toBeDisabled();
  await expect(page.locator('#btn-auto')).toBeDisabled();

  // Select A
  await page.locator(`.photo-card[data-id="${idA}"] .sel-a`).click();
  await expect(page.locator('#img-a')).toBeVisible();
  await expect(page.locator('#slot-a-empty')).toBeHidden();
  await expect(page.locator('#btn-toggle')).toBeDisabled(); // B not set yet

  // Select B
  await page.locator(`.photo-card[data-id="${idB}"] .sel-b`).click();
  await expect(page.locator('#img-b')).toBeVisible();
  await expect(page.locator('#slot-b-empty')).toBeHidden();
  await expect(page.locator('#btn-toggle')).toBeEnabled();
  await expect(page.locator('#btn-auto')).toBeEnabled();

  // Toggle: flicker view appears showing A
  await page.locator('#btn-toggle').click();
  await expect(page.locator('#flicker-view')).toHaveClass(/visible/);
  await expect(page.locator('#flicker-label')).toHaveText('A');

  // Toggle again: switches to B
  await page.locator('#btn-toggle').click();
  await expect(page.locator('#flicker-label')).toHaveText('B');

  // Auto flicker: button becomes active, then stops on second click
  await page.locator('#btn-auto').click();
  await expect(page.locator('#btn-auto')).toHaveClass(/active/);
  await page.locator('#btn-auto').click();
  await expect(page.locator('#btn-auto')).not.toHaveClass(/active/);
});
