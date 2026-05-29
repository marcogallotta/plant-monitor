# UI (browser) test plan

A plan for adding a small, targeted end-to-end browser test suite to the dashboard.

---

## Verdict

Add a **small, narrowly-scoped** browser suite — roughly 6–10 specs — not a broad one.

The existing Vitest + jsdom suite (`backend/tests/js/`) already covers pure logic and DOM
wiring for nearly every module well. We do **not** duplicate any of that in a browser runner;
it would be slower and flakier for no gain.

The one thing jsdom structurally cannot test is **real layout and pointer geometry**, and that
is exactly where the dashboard is most fragile.

---

## The gap

jsdom does no real layout: `getBoundingClientRect()` returns zeros, so the geometry-heavy code
is tested against invented coordinates. See `tests/js/zoom.test.js`, which hand-stubs the rect:

```js
document.getElementById('modal-img').getBoundingClientRect = () => ({ ... })
```

So the most visual, most fragile parts of the dashboard are validated against fake rectangles,
not real rendering:

- **Note pin placement** — `left: x*100%; top: y*100%` over an `inline-block` wrapper sized to
  the rendered image (see `internals.md` → Dashboard). Normalised x/y come from
  `img.getBoundingClientRect()` at click time.
- **`visualToStored()` rotation mapping** (`zoom.js`) — maps clicks in rotated visual space back
  to canonical stored coordinates. The math is unit-tested, but its *premise* — how the browser
  actually lays out a rotated image — is not.
- **Zoom / pan + shift-drag region notes** — real pointer-event sequences and CSS transforms.

A subtle CSS or transform change could break note positioning while every jsdom test stays green.
That bug class is catchable only in a real browser.

---

## Tool: Playwright

- **Brave:** Brave is Chromium/Blink, so it renders like the dev's daily browser. Playwright
  bundles its own Chromium (same engine), which is what we test against for reproducibility.
  We can point it at the local Brave binary via `channel`/`executablePath`, but we won't for
  CI — bundled Chromium gives Brave-equivalent rendering without version drift.
- **Visual regression** built in (`toHaveScreenshot`) — ideal for "did the note pins move?"
  assertions that are otherwise tedious to express.
- **Auto-waiting** removes most flakiness; the trace viewer makes failures easy to debug.
- Real pointer/mouse APIs for the drag/zoom interactions.

Alternatives considered: **Cypress** (heavier, weaker file-upload/multi-tab story, no clean
bundled-Chromium-equals-Brave story), **Vitest browser mode** (promising, still maturing —
revisit later), **Selenium** (no reason to in 2026).

---

## What to test (prioritized)

Cap at the handful of geometry/visual flows where a real browser is the *only* tool that works.

1. **Note pin round-trip** *(top priority — the main reason to do this at all)*
   Click the image at a known spot → pin renders at the expected on-screen position → reload →
   pin still there.
2. **Rotation correctness**
   Rotate a photo, place a note, confirm the `visualToStored` mapping lands the pin correctly in
   real layout. Visual snapshot per rotation (0/90/180/270).
3. **Zoom + pan + shift-drag region note**
   The pointer-physics flow that jsdom fakes.
4. **Modal open / flicker compare (A/B)**
   Smoke test that the core viewing loop works end to end.
5. **Manual upload happy-path**
   Manual upload against the real backend → photo appears in the grid.

**Out of scope:** CRUD, forms, label toggling, events — jsdom already covers these cheaper.
Do not port them to the browser suite.

---

## How it fits the stack

- New `backend/tests/e2e/` (or top-level `e2e/`) directory, with `playwright` as a separate
  devDependency — kept out of the fast `make test-js` path.
- Add a `make test-e2e` target that:
  1. brings up the **test** Docker stack (reuse the isolated `plant-monitoring-test` project),
  2. seeds a couple of photos via `scripts/seed.py`,
  3. runs Playwright against it,
  4. tears the stack down.
- Keep `make test-e2e` **out of** the default `make test` so the inner loop stays fast.
- Run it pre-push / in CI, not on every save.

Per the project's TDD convention, write each spec before the behavior it locks in where practical;
the first spec (note pin round-trip) doubles as the scaffolding example.

---

## Cost / honesty

Browser E2E is the most expensive tier to maintain — slower, occasionally flaky, and screenshot
baselines need updating on intentional UI changes. That is precisely why this plan caps the suite
at the few geometry/visual flows above and leans on the existing Vitest suite for everything else.

---

## Suggested first step

Scaffold: `playwright.config.js` (bundled Chromium, base URL of the test stack), the `make test-e2e`
target wired to the test compose stack, and the **note-pin round-trip** spec as the first example.
