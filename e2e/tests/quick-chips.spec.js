import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';

const FIXTURE_JPG = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../fixtures/400x300.jpg'),
);

async function uploadPhoto(request, date, suffix) {
  const resp = await request.post('/manual-photos', {
    multipart: {
      image: { name: `chip-test-${suffix}.jpg`, mimeType: 'image/jpeg', buffer: Buffer.concat([FIXTURE_JPG, Buffer.from(String(Math.random()))]) },
      captured_at: `${date}T12:00:00Z`,
    },
  });
  expect(resp.status()).toBe(201);
  return resp.json();
}

async function filterByDate(page, date) {
  const settled = page.waitForResponse(
    r => r.url().includes('/photos') && r.url().includes('start=') && r.request().method() === 'GET',
  );
  await page.evaluate((d) => {
    document.getElementById('start').value = d;
    document.getElementById('end').value = d;
    document.getElementById('end').dispatchEvent(new Event('change'));
  }, date);
  await settled;
}

test('unit chip filters grid and Clear deactivates it', async ({ page, request }) => {
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const date = '2099-02-01';
  const unitName = `chip-unit-${runId}`;

  const unitResp = await request.post('/growing-units', { data: { name: unitName } });
  expect(unitResp.status()).toBe(201);
  const unit = await unitResp.json();

  const photo1 = await uploadPhoto(request, date, `${runId}-a`);
  await request.put(`/photos/${photo1.id}`, { data: { growing_unit_ids: [unit.id] } });
  await uploadPhoto(request, date, `${runId}-b`);

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await filterByDate(page, date);
  await expect(page.locator('.photo-card')).toHaveCount(2);

  const chip = page.locator('.qchip', { hasText: unitName });
  await chip.click();
  await expect(page.locator('.photo-card')).toHaveCount(1);
  await expect(chip).toHaveClass(/active/);

  await page.locator('#clear-filter-btn').click();
  await expect(chip).not.toHaveClass(/active/);
});

test('label chip filters grid and clicking again deactivates it', async ({ page, request }) => {
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const date = '2099-02-02';
  const labelName = `chip-label-${runId}`;

  const labelResp = await request.post('/labels', { data: { name: labelName } });
  expect(labelResp.ok()).toBeTruthy();
  const label = await labelResp.json();

  const photo1 = await uploadPhoto(request, date, `${runId}-a`);
  await request.post(`/photos/${photo1.id}/labels/${label.id}`);
  await uploadPhoto(request, date, `${runId}-b`);

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await filterByDate(page, date);
  await expect(page.locator('.photo-card')).toHaveCount(2);

  const chip = page.locator('.qchip', { hasText: labelName });
  await chip.click();
  await expect(page.locator('.photo-card')).toHaveCount(1);
  await expect(chip).toHaveClass(/active/);

  await chip.click();
  await expect(page.locator('.photo-card')).toHaveCount(2);
  await expect(chip).not.toHaveClass(/active/);
});
