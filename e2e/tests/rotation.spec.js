import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

for (const rotation of [90, 180, 270]) {
  test(`pin placed at ${rotation}° maps back to the visual click position`, async ({ page, request }) => {
    const resp = await request.post('/manual-photos', {
      multipart: {
        image: { name: 'rotation-test.jpg', mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
      },
    });
    expect(resp.status()).toBe(201);
    const { id: photoId } = await resp.json();

    await page.goto('/');
    await page.locator(`.photo-card[data-id="${photoId}"] img`).click();
    const modal = page.locator('#modal');
    await expect(modal).toBeVisible();
    await page.waitForFunction(() => {
      const img = document.getElementById('modal-img');
      return img && img.complete && img.naturalWidth > 0;
    });

    // Each cwButton click fires an async updatePhoto(). Use waitForResponse so
    // the DB write completes before we reload to test persistence.
    const cwButton = page.locator('button[title="Rotate clockwise"]');
    for (let i = 0; i < rotation / 90; i++) {
      await Promise.all([
        page.waitForResponse(
          (r) => r.url().includes(`/photos/${photoId}`) && r.request().method() === 'PUT',
        ),
        cwButton.click(),
      ]);
    }
    await page.waitForFunction(
      (deg) => {
        const wrap = document.getElementById('modal-img-wrap');
        return wrap && wrap.style.transform.includes('rotate(' + deg + 'deg)');
      },
      rotation,
    );

    await expect(modal.locator('.note-pin')).toHaveCount(0);

    const imgBox = await page.locator('#modal-img').boundingBox();
    await page.mouse.click(imgBox.x + imgBox.width * 0.3, imgBox.y + imgBox.height * 0.4);

    await expect(modal.locator('#note-panel')).not.toHaveClass(/hidden/);
    await page.locator('#note-text').fill('rotation test note');
    await page.locator('#note-save').click();

    await expect(modal.locator('.note-pin')).toHaveCount(1);
    await assertPinAt(page, 0.3, 0.4);

    // Reload: rotation and note must survive a round-trip through the DB.
    await page.reload();
    await page.locator(`.photo-card[data-id="${photoId}"] img`).click();
    await expect(modal).toBeVisible();
    await page.waitForFunction(() => {
      const img = document.getElementById('modal-img');
      return img && img.complete && img.naturalWidth > 0;
    });
    await page.waitForFunction(
      (deg) => {
        const wrap = document.getElementById('modal-img-wrap');
        return wrap && wrap.style.transform.includes('rotate(' + deg + 'deg)');
      },
      rotation,
    );

    await expect(modal.locator('.note-pin')).toHaveCount(1);
    await assertPinAt(page, 0.3, 0.4);
  });
}

async function assertPinAt(page, expectedX, expectedY) {
  const pinBox = await page.locator('.note-pin').first().boundingBox();
  const imgBox = await page.locator('#modal-img').boundingBox();
  const actualX = (pinBox.x + pinBox.width / 2 - imgBox.x) / imgBox.width;
  const actualY = (pinBox.y + pinBox.height / 2 - imgBox.y) / imgBox.height;
  expect(actualX).toBeCloseTo(expectedX, 1);
  expect(actualY).toBeCloseTo(expectedY, 1);
}
