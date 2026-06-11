# Nursery Direction — strategic context

_A short orientation for the plant-growing direction behind this project._

This doc explains **why** the automation work matters and what nursery direction it supports.

- For irrigation control, water-balance modelling, sparse sensing, canopy/context inputs, and pump
  design, see [`irrigation.md`](irrigation.md).
- For camera monitoring, plant identity, event detection, manual-photo tagging, and AI tagging, see
  [`vision-tagging.md`](vision-tagging.md).

This doc owns: the **strategic rationale that shapes software decisions** — nursery direction,
scaling assumptions, crop buckets as they affect automation, and why irrigation/automation is the
scaling lever.

This doc does **not** own: irrigation formulas, pump hardware, camera pipelines, database schema,
prompts, or implementation sequence. It is also **not** the canonical source for business strategy
or crop selection — those live in [`nursery-north-star.md`](nursery-north-star.md) (thesis, moat,
go-to-market) and [`plant-selection.md`](plant-selection.md) (per-crop calls). This doc summarises
them only as far as they drive software choices; if it ever disagrees with those, they win.

## Who / what

A serious, cooking-led edible-plant project in **Aosta, northern Italy**: alpine-adjacent,
short-season, with real climate constraints.

The long-term direction is a **specialist nursery / high-quality edible-plant operation** over a
3–5+ year horizon. It is run by one person with an unusual skill stack:

- serious cooking
- plant and soil-science theory
- software / embedded / IoT
- data rigour
- fermentation and ingredient-quality obsession

That combination is the edge. The automation work sits exactly at the software-meets-soil
intersection.

Income from software remains primary. The nursery direction is a slow, compounding build, not a
sprint.

## Core thesis

### Demand is not measured by current growing volume

Current use is capped by what has been learned to grow and by available space. A plant’s absence
today is often the **gap to close**, not evidence of low demand.

Current cooking already relies on inferior local substitutes. That is both the demand signal and the
quality-gap thesis.

### Why the crops are hard — and why that drives the software

The interesting crops are warm-tender, short-season, quality-gap crops that are hard to grow well
and hard to source well in northern Italy. **That difficulty is the reason the automation matters:**
reliable propagation, contained heat, and quality-preserving irrigation are what make these crops
growable here at all. The harder the crop, the more the control loop earns its keep.

To be precise about what the difficulty is _not_: it is **not** the business moat. The moat is the
**culinary signal** — knowing which plant, why, and for what dish, backed by real cooking (see
[`nursery-north-star.md`](nursery-north-star.md) §3, Gap B). The claim that hard-to-grow = a
standalone edge is currently unproven and deliberately not front-loaded. For the software the
relevant truth is narrower and solid: these crops are demanding, so the sensing-and-dosing loop has
to be good.

### Quality-first, cooking-led

The cooking is the evidence engine. Better ingredient → better cooking. Crops are prioritised by
whether they materially improve the food, not by novelty alone.

## Crop buckets

| Bucket                                       | Examples                                                        | Gate                                                | Why it matters                                          |
| -------------------------------------------- | --------------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------- |
| **Warm-tender annuals**                      | chillies, aubergine, Southeast Asian / Chinese / Japanese crops | contained-heat propagation skill + heated enclosure | Main R&D lane; high quality gap in northern Italy       |
| **Leafy / veg succession**                   | cilantro, parsley, dill, mint, salad veg                        | area + resowing rhythm                              | Proven demand now; currently rationed and shop-topped   |
| **Slow perennials / woody / immobile crops** | citrus, figs, curry leaf, Sichuan peppercorn, galangal, wasabi  | tenure / permanence                                 | Valuable later, but deferred until non-temporary ground |

The practical priority is:

1. Learn reliable warm-crop propagation and control.
2. Use leafy succession crops as high-frequency learning and eating volume.
3. Defer immobile/perennial commitments until land tenure is stable.

## Scale trajectory

Planning assumptions as of June 2026:

- **Now:** ~4 × 1 m south-facing balcony, ~22 plants, physically maxed.
- **From ~Oct 2026:** likely move toward rented garden/plot space.
- **First serious footprint:** around 100 m².
- **3–4 year target:** roughly 300–500 m² staged use.
- **Long horizon:** possible expansion to Piedmont, especially Turin–Ivrea–Canavese; possibly a
  second site with a hire.

These are planning assumptions, not fixed commitments. The important point is the direction: balcony
→ garden → larger or multi-site operation.

## Why automation / irrigation is the scaling lever

Watering is the one cost that scales almost linearly with plant count and does **not** compress much
with skill.

Sowing is seasonal. Selection improves with experience. Cooking can batch. But watering is daily,
non-deferrable, per-plant, and grows with area.

Twice-daily hand-watering is acceptable on a balcony. At 100 m² it becomes hours of labour. Across
two sites it becomes structurally impossible.

So irrigation is the highest-leverage automation target.

### Strategic implication

Automated irrigation decouples plant count from daily labour. That is the difference between scaling
on hands and scaling on infrastructure.

For this project, irrigation must preserve quality, not just keep plants alive: per-plant or
per-zone control matters because warm-tender crops, leafy succession crops, pots, beds, shaded
areas, and exposed areas will not share the same demand.

The model should therefore be location-portable: weather + forecast + local sensing + known dosing +
observed response, with camera/tagging used as occasional context where useful.

The same sparse-sensing principle matters economically: probes should **calibrate**, not
continuously sense every plant or zone. A few probes establish soil/zone behaviour and drift
anchors, allowing many zones to run from weather, microclimate, sun-map, canopy state, and known
dosing.

The vision/tagging work matters because it supports this loop, but irrigation is the primary
product.

## Current automation state

The balcony is the working miniature of the future garden.

Current system capabilities include:

- overhead Pi camera monitoring
- closeup images for higher-value AI/vision reads
- sparse temperature/humidity sensing across balcony microclimates
- one soil probe as a calibration anchor
- forecast and historical weather integration
- live water-demand modelling
- watering-event inference from EC + soil-moisture response

The next major unlock is **known-input dosing** via pump control.

That changes watering from a noisy inferred event into a measured input:

`sense → dose → measure response → adjust`

Once the system controls the dose, it can learn plant and zone demand curves instead of guessing
from human watering behaviour.

## Camera is context, not the core irrigation sensor

A key design conclusion is that irrigation control should **not** depend on continuous camera
observation.

For the basic control loop — whether a zone has been watered, how much was dosed, and how the soil
responded — the system should rely on known pump input, soil/climate sensing, weather, and forecast
data.

Camera input is still useful, but in a different role: it gives occasional visual context about
**sun exposure, canopy cover, and crop stage**.

Some visual inputs are almost static calibration tasks, such as mapping per-zone sun exposure /
insolation once and updating only when the layout or season materially changes.

A zone of bare soil, newly sown seed, seedlings, moderate canopy, and heavy leaf cover will not have
the same water demand under the same weather. The model does not need perfect daily vision, but it
benefits from periodic reference images that classify zones by coverage and growth state.

This may come from a fixed Pi camera where practical. On a balcony or small greenhouse, one overhead
camera may be enough to give useful reference frames. But that probably will not scale cleanly to
larger plots or multiple sites.

The scalable version may be **requested manual photos**: ask for a picture of a bed, zone, tray, or
plant group when the model needs a visual reference. That only works if the tagging layer can turn
those photos into useful irrigation context:

- which bed, zone, tray, or plant group the photo shows
- what crop or crop mix is present
- whether the area is bare, newly sown, seedlings, moderate canopy, or heavy canopy
- whether anything has moved, been harvested, died back, or changed state

So tagging is not merely a nice camera feature. It is the bridge between occasional human/photos and
irrigation-relevant context.

## Operating constraints

The system must fit the real operating model:

- One-person project.
- No reliable manual logs.
- Balcony now, garden later.
- Pots now, ground later.
- Cold indoor room, usually 14–16°C.
- Warm crops need contained heated propagation, not ambient room heat.
- Future garden may be off-grid or only visited every few days.
- Power, water storage, pressure, and maintenance must be treated as real constraints.
- Edge hardware and outdoor signals are messy; technical handling lives in the irrigation and
  AI/tagging docs.

## Automation priorities from nursery strategy

1. **Irrigation first.** Watering is the daily scaling bottleneck and the highest-stakes
   quality/survival risk.

2. **Known-input dosing before clever inference.** A pump-controlled dose is more valuable than
   endlessly improving inference from messy human watering events.

3. **Sparse probes before dense sensing.** Probes should calibrate soil and zone behaviour, not
   become one-sensor-per-plant infrastructure.

4. **Climate / heated enclosure second.** Warm-tender crops are the moat, but they need controlled
   propagation and protection.

5. **Vision/tagging as support layer.** Camera and AI work should support identity, condition reads,
   harvest/move detection, and irrigation context such as sun exposure, canopy cover, crop stage,
   and zone state. It should not be a hard dependency for basic watering control.

6. **No manual-log dependency.** The system must self-bootstrap from sensors, camera observations,
   known pump events, forecasts, and occasional human corrections or requested photos.

## Goal

Build a practical automation stack that lets a one-person, quality-led edible-plant project scale
from balcony to garden without drowning in daily watering labour.

The core loop is:

`sense → dose → observe → adjust`

The strategic win is not “smart garden gadgetry”. It is making serious, high-quality,
climate-constrained edible growing operationally possible at larger-than-balcony scale.
