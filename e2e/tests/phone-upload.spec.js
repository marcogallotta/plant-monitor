import { test, expect, devices } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

test.use({ ...devices['Pixel 5'] });

test('phone upload: shows Choose photos, uploads appear in grid', async ({ page }) => {
  await page.goto('/');
  await page.locator('.tab-btn[data-tab="import"]').click();

  // Mobile detection should hide desktop buttons and show phone button
  await expect(page.locator('#sd-desktop-row')).toBeHidden();
  await expect(page.locator('#sd-phone-row')).toBeVisible();

  // Set two files on the hidden phone input
  await page.locator('#sd-phone-input').setInputFiles([
    { name: `phone-upload-${Date.now()}-1.jpg`, mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
    { name: `phone-upload-${Date.now()}-2.jpg`, mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
  ]);

  // Thumbs should appear and both be auto-selected
  await expect(page.locator('.sd-thumb-wrap')).toHaveCount(2);
  await expect(page.locator('.sd-thumb-wrap.selected')).toHaveCount(2);

  // Upload
  const [r1, r2] = await Promise.all([
    page.waitForResponse(r => r.url().includes('/manual-photos') && r.request().method() === 'POST'),
    page.waitForResponse(r => r.url().includes('/manual-photos') && r.request().method() === 'POST'),
    page.locator('#sd-upload-btn').click(),
  ]);

  expect(r1.status()).toBe(201);
  expect(r2.status()).toBe(201);

  await expect(page.locator('#sd-upload-status')).toHaveText(/2 uploaded/);

  // Photos appear in gallery
  const id1 = (await r1.json()).id;
  const id2 = (await r2.json()).id;
  await page.locator('.tab-btn[data-tab="gallery"]').click();
  await expect(page.locator(`.photo-card[data-id="${id1}"]`)).toBeVisible();
  await expect(page.locator(`.photo-card[data-id="${id2}"]`)).toBeVisible();
});
