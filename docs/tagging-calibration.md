# Tagging calibration — Tier 1 state

_Last updated: 2026-05-30_

This is the **distilled, always-load** state for AI tagging sessions (see
`docs/ai-tagging-design.md` → "State persistence between sessions"). Read it at the
start of any tagging pass. It churns faster than the design doc — keep it current by
distilling from the `photo_ai_suggestions` corrections (Tier 2).

> **Staleness warning:** this list reflects what was true on the date above. Plants die,
> new ones arrive, and **pots move**. Treat it as a hint; verify against live
> `growing_units` (time-indexed) before trusting it. Reason from each photo's capture
> **date** about what was alive and at what stage then — date is the strongest signal
> for stage/context and the things vision can't see.

---

## Known-plant inventory

Varieties matter — Claude cannot distinguish them from photos alone, so they must be
told. _(TODO: add per-unit sown/propagated/purchased/died dates so reads can be aligned
to a timeline. Pull live data from `GET /assistant/growing-units`.)_

- Sorrel
- French tarragon
- Sage
- Cilantro / coriander
- Peppermint
- Rosemary
- Chives
- Basil (genovese)
- Thai basil
- Thyme
- Lemon thyme
- Bird's eye chilli
- Hangjiao H7 chilli
- Hangjiao H4 chilli
- Lemongrass
- Moroccan mint
- Dill
- Parsley
- Garlic chives
- Welsh onion
- Rau ram
- Rocket
- Fenugreek

## Confirmed container → species bindings (persistent until repot/resow)

The container carries the species; **position does not** (pots move). Disambiguate
look-alikes by container, not location.

- **The two mints:** *peppermint* lives in a **pot**; *Moroccan mint* lives in a
  **trough**. Same-looking foliage — the container is the tell.

_(Extend this as units are registered. This is the durable asset.)_

---

## Confusable rules (learned by correction)

When you hit one of these, **pose a binary/short question rather than committing** — the
offered set has reliably contained the truth (6/6 across calibration rounds). Keep
"unknown" open; never force a plausible-but-wrong pick.

| Looks like | Ask | Notes |
|---|---|---|
| Same-looking mint | peppermint **or** Moroccan mint? | peppermint=pot, Moroccan=trough |
| Fine grassy allium clump | chives / Welsh onion / garlic chives? | near-identical as clumps |
| Lobed apiaceae seedling | parsley **or** cilantro? | near-identical when young |
| Reddish-node stem cuttings | lemongrass **or** rau ram? | both propagate this way |
| Broad oval-leaf seedling | basil **or** chilli? | date-from-sowing resolves it |
| Sprawling reddish stems, sparse leaves, poor condition | rau ram? | rau ram sprawls and reddens under stress |

## Meta-heuristics

- **Binary questions bracket the truth — keep offering them.** What matters is *recall of
  the offered set*, not the model's own pick.
- **Species is the easy part.** Vision is reliable on mature/distinctive plants. The live
  failure modes are **(1) zone undercounting** — missing secondary species at frame edges
  (always scan the edges of a multi-plant shot) — and **(2) stage/context** — seedling vs
  transplant vs mature, condition. Neither is fixed by better looking; use date + timeline
  + hint.
- **One photo = many species, arranged spatially.** Tag per region, not per photo.
- **Not everything is a plant.** Some shots are test/process images (e.g. soil-moisture
  close-ups, repot-in-progress) → **Delete**, don't tag. "No gate" ≠ "no junk."
- **Suggest rotation.** Read with stored `rotation` applied; if upright orientation
  disagrees, emit a `suggested_rotation` (auto-fix on high confidence, queue the rest).

---

## Confirmed examples (few-shot pool)

Ground-truthed by the human across three calibration rounds (2026-05-30). Re-read these
thumbnails as visual priors when tagging the matching species. Filenames are under
`data/photos/`.

### Single / dominant subject
- `554b3a646dc64b3399b6382c3c81ce68.jpg` — **dill**, mature, leggy/floppy
- `291ff4b9585540eab4f55c00347d02ca.jpg` — **Thai basil**, seedlings
- `457790d2c20d4d2090dbf1a87242dcf0.jpg` — **genovese basil**, seedling
- `c9860a82b9594b83a0f0c1658becc874.jpg` — **genovese basil**, young plant
- `b2d470329a6f43c9b3f78bd3a5e47837.jpg` — **chilli**, seedling _(I guessed basil-or-chilli; chilli)_
- `892b874e1bac4f25821c8f744ee3dd9e.jpg` — **chives** clump _(allium binary; chives)_
- `19af7b97567d47f8bf32f2a57db45334.jpg` — **peppermint**, fresh water→soil propagation, **stressed** _(I misread as seedlings — stage error)_
- `7236f3ff21474d17be7ab0e287f728a5.jpg` — **rau ram**, sprawling/stressed
- `db60aae6b3e6418f99c107c3bf2bc039.jpg` — **rau ram**, severely wilted (moved indoors)
- `7faf996c30144613a03c21aad20830ee.jpg` — **lemongrass** cuttings, new nursery purchase

### Multi-species (region-tagged)
- `000cf7f3d4f64299b2d3dd454fd06eab.jpg` — peppermint (top-right pot), fenugreek (top-left trough), rocket (left third middle trough) + cilantro (right 2/3), parsley (middle third bottom trough) + dill (right)
- `ac85543fb0e442549ef03b2f6e56d3ff.jpg` — sage (top-left pot), parsley + dill (right), rocket + cilantro (middle)
- `d630dda5ddf643f2bc4ff61df40cefa7.jpg` — parsley (top 6 cells) + genovese basil (bottom 6)
- `09923168f26e487992fa7c65a9a1237c.jpg` — Moroccan mint (trough), genovese basil (below), Thai basil (bottom-left), Welsh onion (above), rocket (top-right)
- `5e43054b5eb545658514a1681c88a1d9.jpg` — lemongrass, rosemary, sage, peppermint, genovese basil (dense supermarket pot), sorrel (leaf, bottom-right), parsley, chives
- `9b523deb3f3b46db9ecbb8b25916e713.jpg` — parsley / cilantro seedlings (6-cell tray)
- `f6304791e4a64bf18f19172622ec836f.jpg` — Thai basil + genovese basil (one trough)

### Discard (not monitoring photos)
- `34af94c1ded745ee95828eb2a2d41062.jpg` — soil-moisture test close-up → **delete**

---

## Scoreboard so far

18 photos over 3 rounds. Species/confusable calls were strong (every binary held). Misses
were **zone undercounting** and **stage/context** (propagation transplant read as
seedling). Conclusion: invest in region tagging + date-indexed inventory, not in coaxing
better single-label species guesses.
