import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

test('manual upload via dashboard: photo appears in grid', async ({ page }) => {
  await page.goto('/');

  // Expand the upload panel
  await page.locator('.upload-panel-header', { hasText: 'Upload single photo' }).click();
  await expect(page.locator('#upload-form')).toHaveClass(/open/);

  // Intercept the POST before clicking so we don't race the response
  const uploadPromise = page.waitForResponse(
    r => r.url().includes('/manual-photos') && r.request().method() === 'POST',
  );

  await page.locator('#upload-image').setInputFiles({
    name: `dashboard-upload-${Date.now()}.jpg`,
    mimeType: 'image/jpeg',
    buffer: FIXTURE_JPG,
  });
  await page.locator('#upload-form button').click();

  const resp = await uploadPromise;
  expect(resp.status()).toBe(201);
  const { id } = await resp.json();

  await expect(page.locator('#upload-status')).toHaveText('Uploaded.');
  await expect(page.locator(`.photo-card[data-id="${id}"]`)).toBeVisible();
});
