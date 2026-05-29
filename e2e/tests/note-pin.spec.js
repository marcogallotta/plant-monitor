import { test, expect } from '@playwright/test';

// Minimal valid 1×1 white JPEG — enough for the backend to accept and the browser to render.
const MINIMAL_JPEG = Buffer.from(
  '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDB' +
  'kSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAAR' +
  'CAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAA' +
  'AAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAA' +
  'AAAAAAAP/aAAwDAQACEQMRAD8AJQAB/9k=',
  'base64',
);

test('note pin round-trip: placed at known fraction, persists after reload', async ({ page, request }) => {
  const resp = await request.post('/manual-photos', {
    multipart: {
      image: { name: 'pin-test.jpg', mimeType: 'image/jpeg', buffer: MINIMAL_JPEG },
    },
  });
  expect(resp.ok()).toBeTruthy();
  const { id: photoId } = await resp.json();

  await page.goto('/');
  await page.locator(`.photo-card[data-id="${photoId}"] img`).click();
  await expect(page.locator('#modal')).toBeVisible();
  await page.waitForFunction(() => {
    const img = document.getElementById('modal-img');
    return img && img.complete && img.naturalWidth > 0;
  });

  await expect(page.locator('.note-pin')).toHaveCount(0);

  const imgBox = await page.locator('#modal-img').boundingBox();
  await page.mouse.click(imgBox.x + imgBox.width * 0.3, imgBox.y + imgBox.height * 0.4);

  await expect(page.locator('#note-panel')).not.toHaveClass(/hidden/);
  await page.locator('#note-text').fill('geometry test note');
  await page.locator('#note-save').click();

  await expect(page.locator('.note-pin')).toHaveCount(1);
  await assertPinAt(page, 0.3, 0.4);

  await page.reload();
  await page.locator(`.photo-card[data-id="${photoId}"] img`).click();
  await expect(page.locator('#modal')).toBeVisible();
  await page.waitForFunction(() => {
    const img = document.getElementById('modal-img');
    return img && img.complete && img.naturalWidth > 0;
  });

  await expect(page.locator('.note-pin')).toHaveCount(1);
  await assertPinAt(page, 0.3, 0.4);
});

async function assertPinAt(page, expectedX, expectedY) {
  const pinBox = await page.locator('.note-pin').first().boundingBox();
  const wrapBox = await page.locator('#modal-img-wrap').boundingBox();
  const actualX = (pinBox.x + pinBox.width / 2 - wrapBox.x) / wrapBox.width;
  const actualY = (pinBox.y + pinBox.height / 2 - wrapBox.y) / wrapBox.height;
  expect(actualX).toBeCloseTo(expectedX, 1);
  expect(actualY).toBeCloseTo(expectedY, 1);
}
