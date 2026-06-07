# Balcony herb layout

A pot-by-position map of the balcony herbs, so Pi-camera captures can be classified by **location** rather than by guessing species from each frame. The top-down camera angle and resolution make variety-level visual ID unreliable, but the pot positions are stable, so a map built once can be reused across captures.

This is a **snapshot**, not a fixed truth — plants get harvested, replaced, and moved. Re-verify against fresh captures when the garden changes.

> This is a living doc. Claude has free rein to update it as the layout changes — no need to ask first.

## Reading the frame

- The photos are viewed in **landscape**, the same orientation the camera stores them. Left = left, right = right, top = top.
- The **door is at bottom-center** of the frame. The pots run in a row along the far railing.
- The **green shade net is on the right edge** of the frame (it's just shade netting — all pots, no raised bed).
- The **rosemary corner is the far-left end** of the row, opposite the net.
- Walking the row **left → right** goes from the rosemary corner toward the net.

## Conventions

- Usually one plant per pot, but not always (e.g. plain Thyme shares a pot with Lemon Thyme).
- Units not yet in the DB can be added.
- Numbers in parentheses are existing `growing_units.id` values.

## The map (left → right, from the rosemary corner)

### Far-left corner
- Rosemary (1); Sage (37) to its right
- Thyme (38) + Lemon Thyme (13) sharing the ledge pot
- Rau ram (7) below — to be replaced
- Moroccan Mint (17) below that — heavily cut back from heat damage

### Lemongrass cluster
- Lemongrass (21); right of it: Sorrel (8) on top, French tarragon (5) below
- Then Garlic chives (6) + a supermarket Genovese basil (16)

### Middle
- Top: Thai basil vendita (3), Peppermint (19)
- Below: Chives (39), Parsley (20), Dill (4)

### Right / net end
- Welsh onion (18) seedlings right of dill; Cilantro (40) above; Cilantro root (41) right of both
- Rocket (23) below cilantro root
- Left of rocket: 3 basils — Thai basil (15) on the left, two Genovese (16) on the right (labelled "italico" but treated as Genovese)

## Distinguishing features (confusable groups)

For look-alikes, record the features that *actually* separate them — and prefer **position + a hard feature (pot size, scent)** over leaf appearance, which fools even a confident reader. (Worked example: a vision pass once **confidently swapped** lemongrass and garlic chives by grabbing a spurious feature — see below.)

**Lemongrass (21) vs Garlic chives (6)** — routinely confused.
- **Sorrel (8) sits between them** — use it as the divider: lemongrass is on the rosemary side of sorrel, garlic chives toward the net side.
- **Lemongrass = fatter, taller leaves, in a BIGGER pot.** Garlic chives = thinner, shorter blades, smaller pot.
- **Pot size is overhead-readable and stable** → the bigger grassy pot is lemongrass. This is the most reliable overhead tell.
- **Misleading feature to ignore:** length / cascading habit — garlic chives flop and cascade when overgrown, so "long cascading fountain" is NOT lemongrass. Width + pot size + position are the real tells; scent (lemon vs garlic) settles it on the ground.

Other confusable groups (features TBD — fill in as learned):
- Basils: Genovese (16) / Thai basil (15) / Thai basil vendita (3) — vendita flowers with purple spikes.
- Mints: Peppermint (19) / Moroccan mint (17).
- Thyme (38) / Lemon thyme (13) — share a pot; not separable by leaf, needs scent.

## Status notes

- **Spearmint (14) is dead** — retire it.
- **Chillis are mobile.** They sit by the door (bottom-center) in the morning (confirmed in the 2026-06-07 07:00Z / 09:00 local frame — foreground pot cluster absent from the evening frames) and get moved away in the afternoon/night, so they're absent from afternoon/evening captures. Classify by time-of-day + door zone, not a fixed railing slot.
  - Three chilli pots return to the door, **left→right as viewed**: **H4 → H7 → BE** = Hangijiao 4 (34), Hangijiao 7 (35), Birdseye Italico (36). (Confirmed 2026-06-07.)
  - The varieties are **visually identical** — identity is **position-only**, a pure region/lookup, never a vision call. This is the strongest case for region-marking the map.
  - (Units 2, 24–36 are all chilli-related; the seedlings 24–33 are separate.)

## Open items

None outstanding. (The "italico" basils are all treated as Genovese (16).)
