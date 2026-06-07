# Balcony plant data

Per-plant reference data for the balcony herbs: status, pot / quantity notes, and
the features that separate look-alikes. This is the stuff that **isn't** position.

**Positions now live in the DB, not here.** A human-verified set of region tags
(`photo_notes.growing_unit_id`) on the reference Pi frame
`2026-06-07T130010Z.jpg` is the authoritative layout — drawn on a real capture,
machine-readable, and what the system uses. This doc keeps only what those tags
can't express: how to tell confusables apart, plant status, and how many
pots/trays a unit spans.

> Living doc — update freely as the garden changes; no need to ask first.
> Numbers in parentheses are `growing_units.id` values.

## Reading Pi frames (orientation)

- Photos are landscape, as the camera stores them. Left = left, right = right.
- **Door is bottom-center.** Pots run in a row along the far railing.
- **Green shade net is the right edge** (just netting — all pots, no raised bed).
- **Rosemary corner is far-left**, opposite the net. Walking left → right goes
  from the rosemary corner toward the net.
- For *which pot is which*, read the region tags on the reference frame — don't
  re-derive position from prose.

## Inventory & notes

| Unit | Status / notes |
|---|---|
| Rosemary (1) | Far-left corner. |
| Sage (37) | Slow woody perennial — readings stay valid for weeks. |
| Thyme (38) + Lemon thyme (13) | **Share one pot.** Not separable by leaf — needs scent. May be off-screen in some frames. |
| Rau ram (7) | To be replaced. |
| Moroccan mint (17) | Heavily cut back from heat damage. |
| Peppermint (19) | — |
| Lemongrass (21) | One plant. Bigger pot than garlic chives (see below). |
| Sorrel (8) | Sits **between** lemongrass and garlic chives — the divider landmark. |
| French tarragon (5) | — |
| Garlic chives (6) | Thinner blades, smaller pot than lemongrass. |
| Chives (39) | — |
| Welsh onion (18) | Seedlings. |
| Parsley (20) | **Two spots: a main pot + a seedling tray.** |
| Dill (4) | Fast mover — readings go stale in days. |
| Cilantro (40) + Cilantro root (41) | Two units, near the net end. |
| Rocket (23) | Fast mover; bolts in heat (slower under the shade net). |
| Genovese basil (16) | **Three spots: one main pot + two nursery pots** (the "italico" nursery basils are treated as Genovese). |
| Thai basil (15) | Seed-grown. Always a binary review choice vs Genovese / vendita. |
| Thai basil vendita (3) | Distinct cultivar — flowers with **purple spikes**. |
| Chillis: Hangijiao 4 (34), Hangijiao 7 (35), Birdseye Italico (36) | **Mobile** (see status). **Visually identical — identity is position-only**, a region/lookup, never a vision call. |
| Spearmint (14) | **Dead — retired.** |

## Distinguishing features (confusable groups)

For look-alikes, record the features that *actually* separate them — and prefer
**position + a hard feature (pot size, scent)** over leaf appearance, which fools
even a confident reader. (Worked example: a vision pass once **confidently
swapped** lemongrass and garlic chives by grabbing a spurious feature.)

**Lemongrass (21) vs Garlic chives (6)** — routinely confused.
- **Sorrel (8) sits between them** — use it as the divider: lemongrass is on the
  rosemary side of sorrel, garlic chives toward the net side. (Confirmed correct
  in the reference-frame tags.)
- **Lemongrass = fatter, taller leaves, in a BIGGER pot.** Garlic chives =
  thinner, shorter blades, smaller pot.
- **Pot size is overhead-readable and stable** → the bigger grassy pot is
  lemongrass. Most reliable overhead tell.
- **Misleading feature to ignore:** length / cascading habit — garlic chives flop
  and cascade when overgrown, so "long cascading fountain" is NOT lemongrass.
  Width + pot size + position are the real tells; scent (lemon vs garlic) settles
  it on the ground.

Other confusable groups (features TBD — fill in as learned):
- Basils: Genovese (16) / Thai basil (15) / Thai basil vendita (3) — vendita
  flowers with purple spikes.
- Mints: Peppermint (19) / Moroccan mint (17).
- Thyme (38) / Lemon thyme (13) — share a pot; not separable by leaf, needs scent.

## Status notes

- **Spearmint (14) is dead** — retire it.
- **Chillis are mobile.** They get moved around through the day, so their slot in
  the frame changes (and they can be absent from some captures). Because the three
  varieties are visually identical, identity is **position-only** — read it from
  the region tags on whichever frame they appear in, not from a fixed slot. Order
  when lined up left→right: **H4 → H7 → BE** (34 → 35 → 36), confirmed 2026-06-07.
  (Units 2, 24–36 are chilli-related; seedlings 24–33 are separate.)
- **Rau ram (7)** to be replaced; **Moroccan mint (17)** cut back from heat.
