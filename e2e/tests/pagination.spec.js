import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

// Use a date derived from the current time so that re-runs against a
// persisted DB don't accumulate photos on the same day. make test-e2e
// tears down the volume via `down -v`, so this is belt-and-suspenders.
function testDate() {
  const day = String(1 + (Date.now() % 27)).padStart(2, '0');
  return `2099-01-${day}`;
}

test('grid paginates: load more button appears and loads remaining photos', async ({ page, request }) => {
  const date = testDate();
  for (let i = 0; i < 3; i++) {
    const resp = await request.post('/manual-photos', {
      multipart: {
        image: { name: `pagination-test-${i}.jpg`, mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
        captured_at: `${date}T12:00:00Z`,
      },
    });
    expect(resp.status()).toBe(201);
  }

  await page.goto('/?page_size=2');
  // Wait for the initial unfiltered load to settle before applying filters,
  // so the filtered response cannot be overwritten by the unfiltered one.
  await page.waitForLoadState('networkidle');

  // Set both date inputs and dispatch change once, atomically in the browser.
  await page.evaluate((d) => {
    document.getElementById('start').value = d;
    document.getElementById('end').value = d;
    document.getElementById('end').dispatchEvent(new Event('change'));
  }, date);

  await expect(page.locator('.photo-card')).toHaveCount(2);
  await expect(page.locator('.load-more-btn')).toContainText('1 remaining');

  await page.locator('.load-more-btn').click();
  await expect.poll(() => page.locator('.photo-card').count()).toBe(3);
  await expect(page.locator('.load-more-btn')).not.toBeVisible();
});
