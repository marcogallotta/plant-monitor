import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

test.describe.configure({ mode: 'serial' });

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

async function uploadPhoto(request) {
  const resp = await request.post('/manual-photos', {
    multipart: {
      image: { name: 'review-test.jpg', mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
    },
  });
  expect(resp.status()).toBe(201);
  return resp.json();
}

async function ingestSuggestion(request, photoId, overrides = {}) {
  const resp = await request.post('/suggestions/ingest', {
    data: [{ photo_id: photoId, model: 'claude-sonnet-4-6', confidence: 'high', ...overrides }],
  });
  expect(resp.status()).toBe(201);
  return resp.json();
}

async function drainPending(request) {
  const resp = await request.get('/suggestions');
  const suggestions = await resp.json();
  for (const s of suggestions) {
    await request.patch(`/suggestions/${s.id}`, { data: { action: 'reject' } });
  }
}

async function goToReview(page) {
  await page.click('.tab-btn[data-tab="review"]');
  await page.waitForTimeout(600);
}

test('review tab appears in nav and shows empty state', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.tab-btn[data-tab="review"]')).toBeVisible();
  await goToReview(page);
  await expect(page.locator('#review-counter')).toContainText('No pending suggestions');
  await expect(page.locator('.review-empty')).toBeVisible();
});

test('review tab renders suggestion card with plant name and confidence', async ({ page, request }) => {
  await drainPending(request);
  const photo = await uploadPhoto(request);
  await ingestSuggestion(request, photo.id, {
    suggested_plant_name: 'Sorrel',
    observation: 'Plant drooping.',
    suggested_photo_type: 'health_check',
  });

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await goToReview(page);

  await expect(page.locator('#review-counter')).toContainText('1 / 1 pending');
  await expect(page.locator('.review-plant')).toContainText('Sorrel');
  await expect(page.locator('.review-conf-high')).toBeVisible();
  await expect(page.locator('.review-obs')).toContainText('Plant drooping.');
});

test('review tab shows region overlay when bbox present', async ({ page, request }) => {
  await drainPending(request);
  const photo = await uploadPhoto(request);
  await ingestSuggestion(request, photo.id, { x: 0.1, y: 0.1, x2: 0.6, y2: 0.9 });

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await goToReview(page);

  await expect(page.locator('.review-region')).toBeVisible();
});

test('reject button removes card and shows empty state', async ({ page, request }) => {
  await drainPending(request);
  const photo = await uploadPhoto(request);
  await ingestSuggestion(request, photo.id, { suggested_plant_name: 'Dill' });

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await goToReview(page);

  await expect(page.locator('.review-card')).toHaveCount(1);
  await page.click('.review-btn-reject');
  await page.waitForTimeout(600);

  await expect(page.locator('.review-card')).toHaveCount(0);
  await expect(page.locator('#review-counter')).toContainText('No pending suggestions');
});

test('keyboard R rejects current suggestion', async ({ page, request }) => {
  await drainPending(request);
  const photo = await uploadPhoto(request);
  await ingestSuggestion(request, photo.id, { suggested_plant_name: 'Mint' });

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await goToReview(page);

  await expect(page.locator('.review-card')).toHaveCount(1);
  await page.keyboard.press('r');
  await page.waitForTimeout(600);

  await expect(page.locator('.review-card')).toHaveCount(0);
});

test('keyboard A accepts suggestion and writes through photo_type', async ({ page, request }) => {
  await drainPending(request);
  const photo = await uploadPhoto(request);
  await ingestSuggestion(request, photo.id, {
    suggested_plant_name: 'Rosemary',
    suggested_photo_type: 'health_check',
  });

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await goToReview(page);

  await page.keyboard.press('a');
  await page.waitForTimeout(600);

  await expect(page.locator('.review-card')).toHaveCount(0);

  const photoResp = await page.request.get(`/photos?limit=100`);
  const photos = (await photoResp.json()).photos;
  const updated = photos.find(p => p.id === photo.id);
  expect(updated?.photo_type).toBe('health_check');
});

test('delete button removes the photo entirely', async ({ page, request }) => {
  await drainPending(request);
  const photo = await uploadPhoto(request);
  await ingestSuggestion(request, photo.id, { suggested_plant_name: 'Test' });

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await goToReview(page);

  await expect(page.locator('.review-card')).toHaveCount(1);
  page.once('dialog', d => d.accept());
  await page.click('.review-btn-delete');
  await page.waitForTimeout(600);

  await expect(page.locator('.review-card')).toHaveCount(0);

  const delResp = await page.request.delete(`/photos/${photo.id}`);
  expect(delResp.status()).toBe(404);
});

test('gallery tab still works after visiting review tab', async ({ page, request }) => {
  await uploadPhoto(request);
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await goToReview(page);
  await page.click('.tab-btn[data-tab="gallery"]');
  await page.waitForTimeout(400);
  await expect(page.locator('.photo-card').first()).toBeVisible();
});
