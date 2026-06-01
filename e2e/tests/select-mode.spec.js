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
      image: { name: `select-test-${suffix}.jpg`, mimeType: 'image/jpeg', buffer: FIXTURE_JPG },
      captured_at: `${date}T12:00:00Z`,
    },
  });
  expect(resp.status()).toBe(201);
  return resp.json();
}

async function goToDateFiltered(page, date) {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const settled = page.waitForResponse(
    r => r.url().includes('/photos') && r.url().includes('start=') && r.request().method() === 'GET',
  );
  await page.evaluate(d => {
    document.getElementById('start').value = d;
    document.getElementById('end').value = d;
    document.getElementById('end').dispatchEvent(new Event('change'));
  }, date);
  await settled;
}

test('select mode toggle shows and hides the select bar', async ({ page, request }) => {
  const date = '2099-03-01';
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  await uploadPhoto(request, date, runId);

  await goToDateFiltered(page, date);
  await expect(page.locator('#select-bar')).toBeHidden();

  await page.locator('#select-mode-btn').click();
  await expect(page.locator('#select-bar')).toBeVisible();

  await page.locator('#select-mode-btn').click();
  await expect(page.locator('#select-bar')).toBeHidden();
});

test('clicking a card in select mode selects it and updates count', async ({ page, request }) => {
  const date = '2099-03-02';
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const photo = await uploadPhoto(request, date, runId);

  await goToDateFiltered(page, date);
  await page.locator('#select-mode-btn').click();

  const card = page.locator(`.photo-card[data-id="${photo.id}"]`);
  await card.click();
  await expect(card).toHaveClass(/selected/);
  await expect(page.locator('#select-count')).toHaveText('1 selected');
  await expect(page.locator('#delete-selected-btn')).toBeEnabled();
});

test('clicking a selected card deselects it', async ({ page, request }) => {
  const date = '2099-03-03';
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const photo = await uploadPhoto(request, date, runId);

  await goToDateFiltered(page, date);
  await page.locator('#select-mode-btn').click();

  const card = page.locator(`.photo-card[data-id="${photo.id}"]`);
  await card.click();
  await card.click();
  await expect(card).not.toHaveClass(/selected/);
  await expect(page.locator('#select-count')).toHaveText('0 selected');
  await expect(page.locator('#delete-selected-btn')).toBeDisabled();
});

test('select all selects every card', async ({ page, request }) => {
  const date = '2099-03-04';
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  await uploadPhoto(request, date, `${runId}-a`);
  await uploadPhoto(request, date, `${runId}-b`);

  await goToDateFiltered(page, date);
  await page.locator('#select-mode-btn').click();
  await page.getByRole('button', { name: 'Select all' }).click();

  const cards = page.locator('.photo-card');
  await expect(cards).toHaveCount(2);
  for (const card of await cards.all()) {
    await expect(card).toHaveClass(/selected/);
  }
  await expect(page.locator('#select-count')).toHaveText('2 selected');
});

test('delete selected removes photos from the grid', async ({ page, request }) => {
  const date = '2099-03-05';
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const photo = await uploadPhoto(request, date, runId);

  await goToDateFiltered(page, date);
  await page.locator('#select-mode-btn').click();
  await page.locator(`.photo-card[data-id="${photo.id}"]`).click();

  page.on('dialog', d => d.accept());
  await page.locator('#delete-selected-btn').click();

  await expect(page.locator(`.photo-card[data-id="${photo.id}"]`)).toHaveCount(0);
  await expect(page.locator('#select-bar')).toBeHidden();
});

test('cancel exits select mode without deleting', async ({ page, request }) => {
  const date = '2099-03-06';
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const photo = await uploadPhoto(request, date, runId);

  await goToDateFiltered(page, date);
  await page.locator('#select-mode-btn').click();
  await page.locator(`.photo-card[data-id="${photo.id}"]`).click();
  await page.locator('#select-bar').getByRole('button', { name: 'Cancel' }).click();

  await expect(page.locator('#select-bar')).toBeHidden();
  await expect(page.locator(`.photo-card[data-id="${photo.id}"]`)).toBeVisible();
});

test('batch set type applies to all selected photos and preserves selection', async ({ page, request }) => {
  const date = '2099-03-08';
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const p1 = await uploadPhoto(request, date, `${runId}-a`);
  const p2 = await uploadPhoto(request, date, `${runId}-b`);

  await goToDateFiltered(page, date);
  await page.locator('#select-mode-btn').click();
  await page.getByRole('button', { name: 'Select all' }).click();

  const done = page.waitForResponse(
    r => r.url().includes('/photos/batch') && r.request().method() === 'POST',
  );
  await page.locator('#batch-type-select').selectOption('overview');
  const updated = await (await done).json();

  expect(updated.map(p => p.id).sort()).toEqual([p1.id, p2.id].sort());
  expect(updated.every(p => p.photo_type === 'overview')).toBe(true);

  // The control resets to its placeholder and the selection survives for chaining.
  await expect(page.locator('#batch-type-select')).toHaveValue('');
  await expect(page.locator('#select-count')).toHaveText('2 selected');
  await expect(page.locator('#select-bar')).toBeVisible();
});

test('batch add label assigns a label to all selected photos', async ({ page, request }) => {
  const date = '2099-03-09';
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const p1 = await uploadPhoto(request, date, `${runId}-a`);
  const p2 = await uploadPhoto(request, date, `${runId}-b`);

  await goToDateFiltered(page, date);
  await page.locator('#select-mode-btn').click();
  await page.getByRole('button', { name: 'Select all' }).click();

  const done = page.waitForResponse(
    r => r.url().includes('/photos/batch') && r.request().method() === 'POST',
  );
  await page.locator('#batch-label-select').selectOption({ label: 'aphids' });
  const updated = await (await done).json();

  expect(updated.map(p => p.id).sort()).toEqual([p1.id, p2.id].sort());
  expect(updated.every(p => p.labels.some(l => l.name === 'aphids'))).toBe(true);
});

test('drag across two cards selects both', async ({ page, request }) => {
  const date = '2099-03-07';
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const p1 = await uploadPhoto(request, date, `${runId}-a`);
  const p2 = await uploadPhoto(request, date, `${runId}-b`);

  await goToDateFiltered(page, date);
  await page.locator('#select-mode-btn').click();

  const card1 = page.locator(`.photo-card[data-id="${p1.id}"]`);
  const card2 = page.locator(`.photo-card[data-id="${p2.id}"]`);
  const box1 = await card1.boundingBox();
  const box2 = await card2.boundingBox();

  // drag from centre of card1 to centre of card2, stepping through intermediate
  // positions so mouseover fires reliably on both cards
  const x1 = box1.x + box1.width / 2;
  const y1 = box1.y + box1.height / 2;
  const x2 = box2.x + box2.width / 2;
  const y2 = box2.y + box2.height / 2;
  await page.mouse.move(x1, y1);
  await page.mouse.down();
  await page.mouse.move(x1 + (x2 - x1) * 0.5, y1 + (y2 - y1) * 0.5);
  await page.mouse.move(x2, y2);
  await page.mouse.up();

  await expect(card1).toHaveClass(/selected/);
  await expect(card2).toHaveClass(/selected/);
  await expect(page.locator('#select-count')).toHaveText('2 selected');
});
