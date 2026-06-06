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

## Status notes

- **Spearmint (14) is dead** — retire it.
- **Chillis are mobile.** They sit by the door (bottom-center) in the morning and get moved away in the afternoon/night, so they're absent from afternoon/evening captures. They can't be mapped to a fixed pot slot — classify by time-of-day + door zone instead. (Units 2, 24–36 are all chilli-related and not on the railing.)

## Open items

None outstanding. (The "italico" basils are all treated as Genovese (16).)
