import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

// Grid thumbnails point at the rotation-baked variant (?oriented=1) rather than
// CSS-rotating, so that dragging a thumbnail into a browser tab opens it in the
// correct orientation. The dragged/opened URL is exactly the <img> src.
test('rotating a grid photo re-points its thumbnail at the oriented URL', async ({ page, request }) => {
  const resp = await request.post('/manual-photos', {
    multipart: {
      image: { name: 'grid-oriented.jpg', mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
    },
  });
  expect(resp.status()).toBe(201);
  const { id: photoId } = await resp.json();

  await page.goto('/');
  const card = page.locator(`.photo-card[data-id="${photoId}"]`);
  const img = card.locator('img');
  await img.waitFor();

  // Starts unrotated.
  expect(await img.getAttribute('src')).toContain('oriented=1&v=0');

  // Rotate clockwise once via the grid control; wait for the PUT to persist.
  await card.hover();
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes(`/photos/${photoId}`) && r.request().method() === 'PUT',
    ),
    card.locator('.card-rot button:last-child').click(),
  ]);

  // The thumbnail (and therefore the native drag/open target) now uses the rotated variant.
  const src = await img.getAttribute('src');
  expect(src).toContain('oriented=1&v=90');

  // The open/drag path actually serves a rotated JPEG (dimensions swap for a 400x300 source).
  const oriented = await request.get(src);
  expect(oriented.status()).toBe(200);
  expect(oriented.headers()['content-type']).toBe('image/jpeg');
});
