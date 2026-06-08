# Nursery Plan — context brief

_A short orientation for a chat helping with the **automation / irrigation** side of this
project. For the full monitoring + water-balance research detail, see
[ai-tagging-design.md](ai-tagging-design.md)._

## Who / what

A serious, cooking-led edible-plant project in **Aosta, northern Italy** (alpine-adjacent),
heading toward a **specialist nursery** direction over a 3–5+ year horizon. Run by one person
with an unusual skill stack that is the whole point: **serious cook + plant/soil-science theory
+ software / embedded / IoT + data rigour + fermentation**. The automation work sits exactly on
the software-meets-soil intersection.

Income from software remains primary; the nursery is a slow, compounding build, not a sprint.

## The thesis (why the plant choices look the way they do)

- **Demand ≠ current cooking use.** Current use is capped by what's been *learned to grow* and
  by space — not by want. A plant's absence today is the *gap to close*, not low demand. Current
  cooking already runs on **inferior local substitutes**, which is both the demand evidence and
  the quality-gap thesis.
- **The moat is the hard part.** Warm-tender, short-season, quality-gap crops that are hard to
  grow *and* hard to source well in northern Italy. If they were easy, there'd be no edge.
- **Quality-first, cooking-led.** Better ingredient → better cooking; cooking is the evidence
  engine for what's worth growing.

### Three buckets (gating logic — useful for automation prioritisation)

1. **Warm-tender annuals** (chillies, aubergine, SEA/Chinese/Japanese crops) — gated on
   contained-heat propagation skill + a heated enclosure. The R&D moat.
2. **Leafy / veg succession** (cilantro, parsley, dill, mint, salad veg) — gated on garden
   **area** (volume + resow); demand is *proven now* (rationed to ~1 portion/week, shop-topped).
   Works in temporary ground.
3. **Slow perennials / woody / immobile** (rhubarb, citrus, figs, curry leaf, Sichuan
   peppercorn, galangal, wasabi) — gated on **tenure/permanence**; deferred until non-temporary
   ground.

## Scale trajectory

- **Now:** ~4 × 1 m south-facing balcony, ~22 plants, **physically maxed** — no slack space.
- **From ~Oct 2026:** renting a place with garden/plot space; target ~300–500 m² over 3–4 years,
  staged use. First serious footprint likely ~100 m².
- **Long horizon:** possible expansion to **Piedmont** (Turin–Ivrea–Canavese), possibly a second
  site with a hire.

## Why automation / irrigation is the scaling lever (the key point for this chat)

**Watering is the one cost that scales linearly with plant count and does NOT compress with
skill.** Sowing is seasonal, selection improves with experience, cooking batches — but watering
is daily, non-deferrable, per-plant, and grows in lockstep with area. Twice-daily hand-watering
is fine on the balcony, hours/day at 100 m², impossible across two sites.

- **Automating it decouples plant-count from daily labour** → the difference between scaling on
  *hands* vs. scaling on *infrastructure*. It's what makes multi-site feasible.
- **Highest-stakes failure mode** — under/over-watering is the #1 survival/quality risk, worst on
  the warm-tender quality crops that *are* the edge. Per-plant dosing (not garden-average)
  preserves the quality story at scale.
- **Location-portable** — the model (ET₀ × Kc × per-plant sun-fraction + sensor/forecast fusion)
  ports to the garden and to Piedmont. Build once, compounds.

So irrigation is the **highest-leverage piece of the whole stack**; the vision/event-detection
work is the supporting layer.

## Current automation state (summary — detail in ai-tagging-design.md)

- **Overhead Pi camera** (hourly burst-averaged "plates", sway-suppressed) = cheap continuous
  index: identity-by-position, presence, gross change.
- **Closeups + LLM vision** = the value layer: confident ID + harvest/condition reads where
  overhead gives green blobs.
- **Sensors:** SwitchBot temp/humidity at **two balcony micro-climates** (wall = hot/dry, railing
  = cool/exposed; chillis sun-chased to a west window); a **Xiaomi Flower Care soil probe** in the
  cilantro pot (moisture, lux, temp, EC) = the ground-truth calibration anchor.
- **Forecast + sensors** served from an existing **ESP32 home-display server** (Open-Meteo
  forecast + archive; sensor proxy).
- **Water-balance demand side: built & live** — FAO-56 Penman-Monteith **ET₀** from forecast,
  **VPD** per micro-climate, **camera-derived per-region sun-hours**, joined as
  `demand_mm = ET₀ × Kc × sun-fraction`.
- **Supply side:** watering-event detection from the soil probe (built); **auto-pump = the planned
  unlock** — it turns watering from a noisy *inferred* event into **known input**, which lets the
  control loop close (and dissolves the under-vs-over-watering ambiguity).

## The goal

A **closed-loop irrigation controller**: `sense → dose → measure response → adjust`, learning each
plant's demand curve and dosing ahead of the forecast. The balcony is a working miniature of the
100 m² garden.

## Constraints an automation helper should know

- **Cold room kept at 14–16°C** (deliberate); warm crops need a contained heated enclosure, not
  ambient heat.
- **Pi hardware is tiny** (~416 MB RAM, no `cv2`, tmpfs `/tmp`) — algorithms are shaped by this
  (e.g. streaming-mean burst collapse, not median).
- **No manual logs** — the user won't keep watering/harvest logs; everything must self-bootstrap
  from the one soil probe + camera + occasional human corrections.
- **Garden will differ from the balcony:** pots → ground changes the water physics (soil profile,
  drainage, root depth); many zones with sparse sensors instead of two micro-climates; likely
  **off-grid / visited every few days**, so power + water storage/pressure are site constraints.
- **Signal confounds are the hard part** — foliage sway, diurnal lighting (illuminant *colour*),
  camera auto-exposure, registration under moving shadows, wilt-mimics-harvest, the **common-mode
  trap** (detrending that removes lighting also removes events coinciding with a global change).
  See ai-tagging-design.md for how each is handled.
