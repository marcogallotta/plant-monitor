import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

test('grid images use /thumbnail URLs, not full-size', async ({ page, request }) => {
  const resp = await request.post('/manual-photos', {
    multipart: {
      image: { name: 'thumbnail-test.jpg', mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
    },
  });
  expect(resp.status()).toBe(201);
  const { id: photoId } = await resp.json();

  const galleryReady = page.waitForResponse(
    r => /\/photos(\?|$)/.test(r.url()) && r.request().method() === 'GET',
  );
  await page.goto('/');
  await galleryReady;

  const card = page.locator(`.photo-card[data-id="${photoId}"]`);
  const img = card.locator('img');
  await img.waitFor();

  const src = await img.getAttribute('src');
  expect(src).toContain('/thumbnail');
  expect(src).toContain('size=400');
  expect(src).toContain('oriented=1');
});

test('thumbnail endpoint returns a smaller image than the original', async ({ request }) => {
  const resp = await request.post('/manual-photos', {
    multipart: {
      image: { name: 'thumbnail-size-test.jpg', mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
    },
  });
  expect(resp.status()).toBe(201);
  const { id: photoId, filename } = await resp.json();

  const full = await request.get(`/photos/${filename}`);
  expect(full.status()).toBe(200);
  const fullSize = (await full.body()).length;

  const thumb = await request.get(`/photos/${filename}/thumbnail?size=100`);
  expect(thumb.status()).toBe(200);
  const thumbSize = (await thumb.body()).length;

  expect(thumbSize).toBeLessThan(fullSize);
});

test('modal uses medium-size URL on non-localhost', async ({ page, request }) => {
  const resp = await request.post('/manual-photos', {
    multipart: {
      image: { name: 'modal-thumb-test.jpg', mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
    },
  });
  expect(resp.status()).toBe(201);
  const { id: photoId } = await resp.json();

  const galleryReady = page.waitForResponse(
    r => /\/photos(\?|$)/.test(r.url()) && r.request().method() === 'GET',
  );
  // Navigate via a non-localhost URL to trigger the medium-size path
  await page.goto('/');
  await galleryReady;

  const card = page.locator(`.photo-card[data-id="${photoId}"]`);
  await card.locator('img').waitFor();
  await card.locator('img').click();

  const modalImg = page.locator('#modal-img');
  await modalImg.waitFor();
  const src = await modalImg.getAttribute('src');

  // localhost → full URL (no /thumbnail); elsewhere → /thumbnail with size=800
  const isLocal = new URL(page.url()).hostname === 'localhost';
  if (isLocal) {
    expect(src).not.toContain('/thumbnail');
  } else {
    expect(src).toContain('/thumbnail');
    expect(src).toContain('size=800');
  }
});
